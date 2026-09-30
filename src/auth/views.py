"""src/auth/views.py — 인증 시스템 Flask Blueprint (Phase 133).

라우트:
  GET  /auth/login                  로그인 페이지 (3개 소셜 버튼)
  GET  /auth/signup                 가입 페이지 (이메일 + 소셜)
  GET  /auth/<provider>/start       OAuth 시작 (kakao / google / naver)
  GET  /auth/<provider>/callback    OAuth 콜백 → 사용자 생성/로그인 → 세션 발급
  POST /auth/logout                 세션 종료
  GET  /auth/verify-email           이메일 인증 (?token=)
  POST /auth/forgot                 비밀번호 재설정 메일 발송
  GET  /auth/reset                  재설정 페이지 (?token=)
  POST /auth/reset                  새 비밀번호 저장

보안:
  - state 파라미터 CSRF 방어
  - bcrypt 비밀번호 해시 (없으면 hashlib.scrypt 폴백)
  - 세션 쿠키 Secure/HttpOnly/SameSite=Lax
  - ADMIN_EMAILS 환경변수로 관리자 자동 지정
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional
from urllib.parse import urlparse

from flask import (
    Blueprint,
    Response,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
    template_folder="templates",
)

# ---------------------------------------------------------------------------
# 백그라운드 알림 풀 (OAuth 응답을 블로킹하지 않음)
# ---------------------------------------------------------------------------

_notify_pool = ThreadPoolExecutor(
    max_workers=int(os.getenv("OAUTH_NOTIFY_POOL_SIZE", "4")),
    thread_name_prefix="oauth-notify",
)


def _async_notify(fn, *args, **kwargs):
    """알림 함수를 백그라운드 스레드에서 실행. 에러는 로그만."""
    if os.getenv("OAUTH_NOTIFY_ASYNC", "1") == "0":
        # 동기 모드 (테스트용)
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("notify failed (sync mode)")
        return
    try:
        future = _notify_pool.submit(fn, *args, **kwargs)

        def _log_exc(f):
            exc = f.exception()
            if exc:
                logger.warning("async notify exception: %s", exc)

        future.add_done_callback(_log_exc)
    except Exception:
        logger.exception("notify submit failed")


# ---------------------------------------------------------------------------
# 헬퍼: 비밀번호 해시
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    """bcrypt 또는 hashlib.scrypt 폴백으로 비밀번호 해시."""
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        salt = os.urandom(16)
        key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
        return salt.hex() + ":" + key.hex()


def _verify_password(password: str, stored_hash: str) -> bool:
    """비밀번호 검증."""
    if not stored_hash:
        return False
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    except ImportError:
        try:
            salt_hex, key_hex = stored_hash.split(":", 1)
            salt = bytes.fromhex(salt_hex)
            key = bytes.fromhex(key_hex)
            new_key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
            return secrets.compare_digest(key, new_key)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# 헬퍼: 관리자 여부
# ---------------------------------------------------------------------------

def _is_admin_email(email: str) -> bool:
    """ADMIN_EMAILS 환경변수에 포함된 이메일이면 admin."""
    admin_emails_raw = os.getenv("ADMIN_EMAILS", "")
    admin_emails = [e.strip().lower() for e in admin_emails_raw.split(",") if e.strip()]
    return email.lower() in admin_emails


def _resolve_user_role(email: str, provider: str = "", provider_user_id: str = "") -> str:
    """admin_resolver를 통해 역할 결정. ADMIN_EMAILS / 소셜ID / BOOTSTRAP_EMAIL 모두 체크."""
    from .admin_resolver import resolve_role_for_login
    return resolve_role_for_login(email, provider=provider, provider_user_id=provider_user_id)


def establish_session(user, role: Optional[str] = None, remember: bool = False) -> None:
    """사용자 세션 공통 설정.

    remember(자동 로그인) 또는 관리자일 때만 영구 세션(브라우저 닫아도 유지).
    그 외 소비자는 브라우저 세션 쿠키 → 브라우저 종료/캐시 갱신 시 재로그인(개인정보 보호).
    """
    resolved_role = role or getattr(user, "role", "seller")
    session["user_id"] = getattr(user, "user_id", "")
    # C-F19: 이메일이 비어 오면 **정체성 표**에서 대표 이메일을 가져다 싣는다.
    #   여기서 한 번 채워 두면 화면을 그릴 때마다 다시 물을 일이 없다(쿼리 0).
    _mail = getattr(user, "email", "") or ""
    if not _mail:
        try:
            from .identity import profile as _idprof
            _mail = _idprof(getattr(user, "user_id", "")).get("email", "") or ""
        except Exception:
            _mail = ""
    session["user_email"] = _mail
    session["user_name"] = getattr(user, "name", "")
    session["user_role"] = resolved_role
    session.permanent = bool(remember) or (resolved_role == "admin")


# ---------------------------------------------------------------------------
# 헬퍼: 현재 로그인 사용자
# ---------------------------------------------------------------------------

def get_current_user():
    """세션에서 현재 사용자 반환 (없으면 None)."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        from .user_store import get_store
        return get_store().find_by_id(user_id)
    except Exception:
        return None


def _safe_next_url(next_url: str, default: str = "/seller/dashboard") -> str:
    """리다이렉트 대상이 내부 URL인지 검증 (open redirect 방어).

    외부 도메인으로의 리다이렉트를 차단하고, 안전한 내부 경로만 허용.

    Examples::
        _safe_next_url("https://evil.com") -> "/seller/dashboard"  # 외부 URL 차단
        _safe_next_url("//evil.com/path")  -> "/seller/dashboard"  # 프로토콜 상대 URL 차단
        _safe_next_url("/seller/me")       -> "/seller/me"          # 내부 경로 허용
        _safe_next_url("")                 -> "/seller/dashboard"   # 빈 값 → 기본값
    """
    if not next_url:
        return default
    try:
        candidate = next_url.strip()
        parsed = urlparse(candidate)
        allowed_prefixes = ("/", "/seller/", "/admin/", "/auth/")
        if (
            parsed.scheme
            or parsed.netloc
            or not candidate.startswith("/")
            or candidate.startswith("//")
            or "\\" in candidate
            or not any(candidate == prefix or candidate.startswith(prefix) for prefix in allowed_prefixes)
        ):
            return default
        return candidate
    except Exception:
        return default


def _oauth_default_next(provider: str) -> str:
    """OAuth 프로바이더별 기본 이동 경로."""
    provider = (provider or "").strip().lower()
    if provider == "kakao":
        return os.getenv("KAKAO_OAUTH_NEXT_DEFAULT", "/seller/dashboard").strip() or "/seller/dashboard"
    if provider == "google":
        return os.getenv("GOOGLE_OAUTH_NEXT_DEFAULT", "/seller/dashboard").strip() or "/seller/dashboard"
    if provider == "naver":
        return os.getenv("NAVER_OAUTH_NEXT_DEFAULT", "/seller/dashboard").strip() or "/seller/dashboard"
    if provider == "apple":
        return os.getenv("APPLE_OAUTH_NEXT_DEFAULT", "/seller/dashboard").strip() or "/seller/dashboard"
    return "/seller/dashboard"


def _popup_redirect_response(next_url: str) -> Response:
    safe_next = _safe_next_url(next_url, default="/seller/dashboard")
    safe_next_js = json.dumps(safe_next, ensure_ascii=False)
    html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>OAuth 완료</title></head>
<body><script>
if (window.opener && !window.opener.closed) {{
  window.opener.location.href = {safe_next_js};
  window.close();
}} else {{
  window.location.href = {safe_next_js};
}}
</script></body></html>"""
    return Response(html, mimetype="text/html; charset=utf-8")


# ---------------------------------------------------------------------------
# 인증 데코레이터
# ---------------------------------------------------------------------------

def require_login(f):
    """로그인 필수 데코레이터."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated


def require_role(role: str):
    """특정 역할 필수 데코레이터."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("auth.login", next=request.url))
            user = get_current_user()
            if not user or user.role != role:
                return jsonify({"error": "권한이 없습니다."}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ---------------------------------------------------------------------------
# 프로바이더 팩토리
# ---------------------------------------------------------------------------

_PROVIDER_MAP = {
    "kakao": None,
    "google": None,
    "naver": None,
    "apple": None,
}


def _get_provider(provider: str):
    """프로바이더 인스턴스 반환."""
    try:
        if provider == "kakao":
            from .providers.kakao import KakaoProvider
            return KakaoProvider()
        elif provider == "google":
            from .providers.google import GoogleProvider
            return GoogleProvider()
        elif provider == "naver":
            from .providers.naver import NaverProvider
            return NaverProvider()
        elif provider == "apple":
            from .providers.apple import AppleProvider
            return AppleProvider()
    except Exception as exc:
        logger.warning("프로바이더 로드 실패 (%s): %s", provider, exc)
    return None


_OAUTH_FALLBACK_BASE = "https://kohganepercentiii.com"


def _resolve_oauth_base_url() -> str:
    """OAuth 콜백 베이스 URL을 결정한다.

    우선순위:
    1. OAUTH_REDIRECT_BASE_URL env (콜백 베이스 전용)
    2. APP_BASE_URL env (앱 전반 베이스)
    3. 현재 요청 컨텍스트 — request.scheme/host (ProxyFix 가 적용돼 있으므로
       X-Forwarded-Proto/Host가 올바르게 반영된다)
    4. 폴백 (https://kohganepercentiii.com)

    정규화: host 소문자, 끝슬래시 제거, scheme 강제(https; localhost/127.0.0.1은 http 허용).
    www 유무는 임의로 변경하지 않는다 — 운영자가 콘솔에 그 값을 등록하면 된다.
    """
    # 1. 명시적 콜백 전용 env
    base = os.getenv("OAUTH_REDIRECT_BASE_URL", "").strip().rstrip("/")
    # 2. 앱 공통 베이스 URL
    if not base:
        base = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    # 3. 요청 컨텍스트에서 유도
    if not base:
        try:
            scheme = request.scheme  # ProxyFix 적용 시 X-Forwarded-Proto 반영
            host = request.host    # host(:port) 그대로
            base = f"{scheme}://{host}"
        except RuntimeError:
            pass  # 요청 컨텍스트 없음 (배치/테스트)
    # 4. 폴백
    if not base:
        base = _OAUTH_FALLBACK_BASE

    # 정규화: host 소문자, scheme 강제
    parsed = urlparse(base)
    host_lc = parsed.netloc.lower()
    scheme = parsed.scheme or "https"
    _local = host_lc.startswith("localhost") or host_lc.startswith("127.0.0.1")
    if not _local and scheme != "https":
        scheme = "https"
    return f"{scheme}://{host_lc}"


def _callback_uri(provider: str) -> str:
    """OAuth 콜백 URI 생성 (단일 소스 — start/callback 공유).

    _resolve_oauth_base_url() 의 우선순위·정규화 로직을 그대로 사용하여
    oauth_start 와 oauth_callback 이 항상 동일한 URI 를 전달함을 보장한다.
    """
    base = _resolve_oauth_base_url()
    return f"{base}/auth/{provider}/callback"


_OAUTH_PROVIDER_ENV_SPECS = {
    "google": {
        "display_name": "Google",
        "client_id_envs": [
            ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID"),
            ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_ID (레거시 폴백)"),
        ],
        "client_secret_envs": [
            ("GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET"),
            ("GOOGLE_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET (레거시 폴백)"),
        ],
    },
    "kakao": {
        "display_name": "Kakao",
        "client_id_envs": [
            ("KAKAO_REST_API_KEY", "KAKAO_REST_API_KEY"),
            ("KAKAO_OAUTH_CLIENT_ID", "KAKAO_OAUTH_CLIENT_ID (별칭 폴백)"),
        ],
        "client_secret_envs": [
            ("KAKAO_CLIENT_SECRET", "KAKAO_CLIENT_SECRET"),
            ("KAKAO_OAUTH_CLIENT_SECRET", "KAKAO_OAUTH_CLIENT_SECRET (별칭 폴백)"),
        ],
    },
    "naver": {
        "display_name": "Naver",
        "client_id_envs": [
            ("NAVER_CLIENT_ID", "NAVER_CLIENT_ID"),
            ("NAVER_OAUTH_CLIENT_ID", "NAVER_OAUTH_CLIENT_ID (별칭 폴백)"),
        ],
        "client_secret_envs": [
            ("NAVER_CLIENT_SECRET", "NAVER_CLIENT_SECRET"),
            ("NAVER_OAUTH_CLIENT_SECRET", "NAVER_OAUTH_CLIENT_SECRET (별칭 폴백)"),
        ],
    },
    "apple": {
        "display_name": "Apple",
        "client_id_envs": [
            ("APPLE_CLIENT_ID", "APPLE_CLIENT_ID (Services ID)"),
        ],
        "client_secret_envs": [
            ("APPLE_CLIENT_SECRET", "APPLE_CLIENT_SECRET (또는 .p8: APPLE_TEAM_ID/KEY_ID/PRIVATE_KEY)"),
            ("APPLE_PRIVATE_KEY", "APPLE_PRIVATE_KEY (.p8)"),
        ],
    },
}


def _oauth_env_value(name: str) -> str:
    return os.getenv(name, "").strip()


def _get_first_set_oauth_env(envs: list[tuple[str, str]]) -> tuple[str, str]:
    for env_name, label in envs:
        value = _oauth_env_value(env_name)
        if value:
            return value, label
    return "", ""


def _secret_hint(secret: str) -> str:
    secret = (secret or "").strip()
    if not secret:
        return "미설정"
    if len(secret) < 4:
        return "설정됨 (끝 ****)"
    return f"설정됨 (끝 {secret[-4:]})"


def _env_value_mismatch(primary_env: str, legacy_env: str) -> bool:
    if not primary_env or not legacy_env:
        return False
    primary = _oauth_env_value(primary_env)
    legacy = _oauth_env_value(legacy_env)
    return bool(primary and legacy and primary != legacy)


def _oauth_runtime(provider: str) -> dict:
    provider = (provider or "").strip().lower()
    spec = _OAUTH_PROVIDER_ENV_SPECS.get(provider, {})
    client_id_envs = spec.get("client_id_envs", [])
    client_secret_envs = spec.get("client_secret_envs", [])
    provider_instance = _get_provider(provider)
    runtime_client_id = (getattr(provider_instance, "client_id", "") or "").strip()
    runtime_client_secret = (getattr(provider_instance, "client_secret", "") or "").strip()
    env_client_id, client_id_active_env = _get_first_set_oauth_env(client_id_envs)
    env_client_secret, client_secret_active_env = _get_first_set_oauth_env(client_secret_envs)
    primary_client_id_env = client_id_envs[0][0] if client_id_envs else ""
    primary_client_secret_env = client_secret_envs[0][0] if client_secret_envs else ""
    legacy_client_id_env = client_id_envs[1][0] if len(client_id_envs) > 1 else ""
    legacy_client_secret_env = client_secret_envs[1][0] if len(client_secret_envs) > 1 else ""
    client_id = runtime_client_id or env_client_id
    client_secret = runtime_client_secret or env_client_secret
    client_id_env_help = " / ".join(env_name for env_name, _label in client_id_envs)
    client_secret_env_help = " / ".join(env_name for env_name, _label in client_secret_envs)
    return {
        "provider": provider,
        "display_name": spec.get("display_name", provider.title()),
        "configured": bool(provider_instance and provider_instance.is_configured),
        "callback_url": _callback_uri(provider),
        "client_id": client_id,
        "client_id_set": bool(client_id),
        "client_id_env": primary_client_id_env,
        "client_id_active_env": client_id_active_env,
        "client_id_missing_message": f"미설정 — {client_id_env_help}" if client_id_env_help else "미설정",
        "legacy_client_id_env": legacy_client_id_env,
        "standard_client_id": _oauth_env_value(primary_client_id_env),
        "legacy_client_id": _oauth_env_value(legacy_client_id_env),
        "client_id_mismatch": _env_value_mismatch(primary_client_id_env, legacy_client_id_env),
        "client_secret_set": bool(client_secret),
        "client_secret_env": primary_client_secret_env,
        "client_secret_active_env": client_secret_active_env,
        "client_secret_missing_message": (
            f"미설정 — {client_secret_env_help}" if client_secret_env_help else "미설정"
        ),
        "legacy_client_secret_env": legacy_client_secret_env,
        "client_secret_hint": _secret_hint(client_secret),
        "standard_client_secret_hint": _secret_hint(_oauth_env_value(primary_client_secret_env)),
        "legacy_client_secret_hint": _secret_hint(_oauth_env_value(legacy_client_secret_env)),
        "client_secret_mismatch": _env_value_mismatch(primary_client_secret_env, legacy_client_secret_env),
    }


def _provider_status(provider: str) -> dict:
    """로그인 화면용 프로바이더 상태."""
    provider = (provider or "").strip().lower()
    p = _get_provider(provider)
    is_configured = bool(p and p.is_configured)
    setup_url = "/admin/oauth-setup"
    if is_configured:
        return {"is_configured": True, "reason": "", "setup_url": setup_url}

    reason_map = {
        "kakao": "카카오 OAuth 설정이 없습니다.",
        "google": "구글 OAuth 설정이 없습니다.",
        "naver": "네이버 OAuth 설정이 없습니다.",
    }
    return {
        "is_configured": False,
        "reason": reason_map.get(provider, "OAuth 설정이 없습니다."),
        "setup_url": setup_url,
    }


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------

def _login_page(*, status: int = 200, error: str = "", error_code: str = "", notice: str = "",
                email: str = "", next_url: str = "", resend: bool = False):
    """로그인 화면 — 오류는 **이 응답 안에** 적는다(AUTH-1).

    전엔 오류를 flash에 싣고 302로 되돌렸다. flash는 세션 쿠키를 타므로 쿠키가 어긋나면
    오류까지 사라져 「그냥 새로고침」처럼 보인다. 이제 POST 실패는 같은 응답에서 원인 코드와 함께 보인다.
    """
    show_diag = request.args.get("diag") == "1"
    if not show_diag:
        try:
            from .admin_resolver import is_admin_session
            show_diag = is_admin_session(session)[0]
        except Exception:
            show_diag = False
    oauth_runtime = None
    if show_diag:
        oauth_runtime = {
            "kakao": _oauth_runtime("kakao"),
            "google": _oauth_runtime("google"),
            "naver": _oauth_runtime("naver"),
        }
    return render_template(
        "auth/login.html",
        next_url=next_url,
        kakao_status=_provider_status("kakao"),
        google_status=_provider_status("google"),
        naver_status=_provider_status("naver"),
        apple_status=_provider_status("apple"),
        oauth_runtime=oauth_runtime,
        auth_error=error, auth_error_code=error_code, auth_notice=notice,
        auth_email_value=email, auth_resend=resend,
    ), status


def _signup_page(*, status: int = 200, error: str = "", error_code: str = "", email: str = "",
                 name: str = "", next_url: str = ""):
    return render_template(
        "auth/signup.html",
        kakao_status=_provider_status("kakao"),
        google_status=_provider_status("google"),
        naver_status=_provider_status("naver"),
        next_url=next_url,
        auth_error=error, auth_error_code=error_code,
        auth_email_value=email, auth_name_value=name,
    ), status


def _why(exc: Exception) -> str:
    """저장소 예외 한 줄 — 비밀(접속 문자열·토큰)은 빼고 종류와 첫 줄만."""
    try:
        from src.collectors.secret_scrub import scrub_line
        msg = scrub_line(str(exc).splitlines()[0] if str(exc) else "")
    except Exception:
        msg = ""
    import re as _re
    # 접속 문자열(자격 포함 주소)은 통째로 가린다 — 스킴을 가리지 않고 `xxx://…` 전부.
    msg = _re.sub(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://\S+", "<주소 생략>", msg)[:160]
    return f"{type(exc).__name__}: {msg}".strip().rstrip(":")


_SOCIAL_NAMES = {"google": "구글", "kakao": "카카오", "naver": "네이버", "apple": "애플"}


def _social_provider_for(email: str) -> str:
    """이 이메일이 **소셜로만** 등록돼 있으면 그 프로바이더 이름(한국어), 아니면 빈 문자열."""
    try:
        from src.db import user_identities_pg as ident
        for prov in ("google", "kakao", "naver", "apple"):
            if ident.resolve(prov, email):
                return _SOCIAL_NAMES[prov]
    except Exception:
        pass
    return ""


@auth_bp.get("/login")
def login():
    """로그인 페이지."""
    if session.get("user_id"):
        return redirect(_safe_next_url(request.args.get("next", "")))
    return _login_page(next_url=_safe_next_url(request.args.get("next", "")))


@auth_bp.get("/signup")
def signup():
    """회원가입 페이지."""
    if session.get("user_id"):
        return redirect(_safe_next_url(request.args.get("next", "")))
    return _signup_page(next_url=_safe_next_url(request.args.get("next", "")))


@auth_bp.post("/signup")
def signup_post():
    """이메일 + 비밀번호 회원가입 → **바로 로그인**(오너 결정 ㊼, 2026-09-30).

    계정은 PG `password_accounts`에 적고 **다시 읽어 확인한 뒤에만** 로그인시킨다.
    실패는 삼키지 않는다 — 원인 코드와 한국어 원문을 이 응답에 적는다.
    """
    from . import password_accounts as accounts
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    name = request.form.get("name", "").strip() or email.split("@")[0]
    next_url = _safe_next_url(request.form.get("next", ""))
    page = dict(email=email, name=request.form.get("name", "").strip(), next_url=next_url)

    if not email or "@" not in email or not password:
        return _signup_page(status=400, error_code="AUTH-SIGNUP-EMPTY",
                            error="이메일과 비밀번호를 입력해 주세요.", **page)
    if len(password) < 8:
        return _signup_page(status=400, error_code="AUTH-SIGNUP-SHORT",
                            error="비밀번호는 8자 이상이어야 합니다.", **page)

    try:
        existing = accounts.find(email)
    except accounts.StoreDown as exc:
        logger.warning("[auth] signup store-down: %s", exc)
        return _signup_page(status=503, error_code="AUTH-STORE-DOWN",
                            error=f"계정 저장소에 연결하지 못했어요 — {_why(exc)}", **page)
    if existing:
        return _login_page(status=409, error_code="AUTH-SIGNUP-EXISTS", email=email, next_url=next_url,
                           error="이미 가입된 이메일입니다 — 아래에서 비밀번호로 로그인해 주세요.")
    social = _social_provider_for(email)
    if social:
        return _login_page(status=409, error_code="AUTH-SIGNUP-SOCIAL", email=email, next_url=next_url,
                           error=f"이 이메일은 {social}로 가입돼 있어요 — 위의 「{social}로 로그인」을 눌러 주세요.")

    # 정본 user_id: 정체성 표가 이 (password, email)을 이미 알면 그 값(옛 가입이 계정 행만 잃은 경우).
    #   그 user_id가 **데이터를 쥐고 있으면** 비밀번호만으로 넘겨주지 않는다(남의 데이터로 들어가는 길).
    from .models import User
    user_id = ""
    try:
        from .identity import _counts_for
        from src.db import user_identities_pg as ident
        prior = ident.resolve("password", email)
        if prior:
            held = any(int(v or 0) != 0 for v in (_counts_for(prior) or {}).values())   # -1(못 셈)도 있다고 본다
            if held:
                logger.warning("[auth] signup orphan-identity with data uid=%s…", prior[:8])
                return _signup_page(status=409, error_code="AUTH-SIGNUP-ORPHAN",
                                    error="이 이메일로 만든 데이터가 있는데 계정 기록이 없어요 — "
                                          "운영자에게 이 코드를 알려 주세요.", **page)
            user_id = prior
    except Exception as exc:
        logger.warning("[auth] signup 정체성 확인 실패(새 계정으로 진행): %s", exc)
    role = "admin" if _is_admin_email(email) else "seller"
    user = User.new(email=email, name=name, role=role)
    if user_id:
        user.user_id = user_id
    verify_token = secrets.token_urlsafe(32)
    try:
        acct = accounts.create(user_id=user.user_id, email=email, password_hash=_hash_password(password),
                               name=name, role=role, verify_token=verify_token)
    except accounts.AccountExists:
        return _login_page(status=409, error_code="AUTH-SIGNUP-EXISTS", email=email, next_url=next_url,
                           error="이미 가입된 이메일입니다 — 아래에서 비밀번호로 로그인해 주세요.")
    except Exception as exc:
        logger.warning("[auth] signup 저장 실패: %s", exc)
        return _signup_page(status=503, error_code="AUTH-SIGNUP-SAVE",
                            error=f"계정을 저장하지 못했어요 — {_why(exc)}", **page)

    from .identity import known_email as _known, register_login as _reg
    was_known = _known(email)
    _reg("password", email, acct["user_id"], display_name=name)

    if accounts.require_email_verify():
        logger.info("[auth] signup 인증 메일: %s", _send_verify_mail(email, name, verify_token))

    if not was_known:
        try:
            from src.notifications.telegram import send_telegram
            _async_notify(
                send_telegram,
                f"🆕 신규 셀러 가입\n이메일: {email}\n이름: {name}\n경로: 이메일 가입",
                urgency="info",
            )
        except Exception:
            pass

    user.user_id, user.email, user.name, user.role = acct["user_id"], email, name, role
    establish_session(user, role=role, remember=True)
    logger.info("[auth] signup ok uid=%s… → %s", acct["user_id"][:8], next_url)
    # flash는 싣지 않는다 — 콘솔 화면은 flash를 그리지 않아, 남은 「가입 완료」가 나중 로그인 화면에 뜬다.
    #   대시보드에 들어간 것 자체가 결과다.
    return redirect(next_url)


def _send_verify_mail(email: str, name: str, token: str) -> str:
    """인증 메일 — 보낸 결과를 **한 문장으로** 돌려준다(무음 실패 금지)."""
    try:
        from src.notifications.email_resend import send_email
        verify_url = f"{os.getenv('APP_BASE_URL', 'https://kohganepercentiii.com')}/auth/verify-email?token={token}"
        ok = send_email(
            to=email,
            subject="[고가브릿지] 이메일 인증",
            html=f"<p>안녕하세요, {name}님!</p>"
                 f"<p>아래 링크를 클릭하여 이메일을 인증해주세요:</p>"
                 f"<p><a href='{verify_url}'>이메일 인증하기</a></p>",
            text=f"이메일 인증: {verify_url}",
        )
    except Exception as exc:
        logger.warning("[auth] 인증 메일 발송 예외: %s", exc)
        return f"인증 메일을 보내지 못했어요(AUTH-MAIL-FAIL: {type(exc).__name__})."
    if not ok:
        return "인증 메일을 보내지 못했어요(AUTH-MAIL-OFF: 메일 발송 설정이 꺼져 있거나 거절됨)."
    return "인증 메일을 보냈어요."


@auth_bp.post("/login")
def login_post():
    """이메일 + 비밀번호 로그인 — 오류를 **셋으로 가른다**(오너 2026-09-30).

    등록되지 않은 이메일 / 비밀번호 틀림 / (플래그 켜진 경우만) 이메일 인증 필요.
    한 문구로 뭉개면 「가입은 됐는데 로그인이 안 된다」를 아무도 가르지 못한다.
    """
    from . import password_accounts as accounts
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    next_url = _safe_next_url(request.form.get("next", ""))

    if not email or not password:
        return _login_page(status=400, error_code="AUTH-LOGIN-EMPTY", email=email, next_url=next_url,
                           error="이메일과 비밀번호를 입력해 주세요.")
    try:
        acct = accounts.find(email)
    except accounts.StoreDown as exc:
        logger.warning("[auth] login store-down: %s", exc)
        return _login_page(status=503, error_code="AUTH-STORE-DOWN", email=email, next_url=next_url,
                           error=f"계정 저장소에 연결하지 못했어요 — {_why(exc)}")
    if not acct:
        social = _social_provider_for(email)
        if social:
            return _login_page(status=401, error_code="AUTH-LOGIN-SOCIAL", email=email, next_url=next_url,
                               error=f"이 이메일은 {social}로 가입돼 있어요 — 위의 「{social}로 로그인」을 눌러 주세요.")
        return _login_page(status=401, error_code="AUTH-LOGIN-NO-ACCOUNT", email=email, next_url=next_url,
                           error="등록되지 않은 이메일입니다 — 아래 「회원가입」에서 먼저 가입해 주세요.")
    if not _verify_password(password, acct.get("password_hash", "")):
        return _login_page(status=401, error_code="AUTH-LOGIN-BAD-PASSWORD", email=email, next_url=next_url,
                           error="비밀번호가 틀립니다 — 잊으셨으면 아래 「비밀번호 재설정」을 눌러 주세요.")
    if accounts.require_email_verify() and not acct.get("email_verified"):
        return _login_page(status=403, error_code="AUTH-LOGIN-UNVERIFIED", email=email, next_url=next_url,
                           resend=True, error="이메일 인증이 필요합니다 — 받은 메일의 링크를 눌러 주세요.")

    from .models import User
    # 정본 user_id는 정체성 표 먼저(C-F19) — 계정 행의 값과 다르면 표가 이긴다.
    uid = acct["user_id"]
    try:
        from src.db import user_identities_pg as ident
        uid = ident.resolve("password", email) or uid
    except Exception:
        pass
    user = User(user_id=uid, email=email, name=acct.get("name", ""), role=acct.get("role") or "seller",
                email_verified=bool(acct.get("email_verified")))
    role = "admin" if (acct.get("role") == "admin" or _is_admin_email(email)) else (acct.get("role") or "seller")
    remember = str(request.form.get("remember", "")).lower() in ("1", "on", "true", "yes")
    establish_session(user, role=role, remember=remember)
    accounts.touch_login(email)
    logger.info("[auth] login ok uid=%s… → %s", uid[:8], next_url)
    return redirect(next_url)


@auth_bp.post("/verify-email/resend")
def verify_email_resend():
    """인증 메일 다시 보내기 — 플래그가 켜진 경우에만 로그인 화면이 이 버튼을 보인다."""
    from . import password_accounts as accounts
    email = request.form.get("email", "").strip().lower()
    try:
        acct = accounts.find(email)
    except accounts.StoreDown as exc:
        return _login_page(status=503, error_code="AUTH-STORE-DOWN", email=email,
                           error=f"계정 저장소에 연결하지 못했어요 — {_why(exc)}")
    if not acct:
        return _login_page(status=404, error_code="AUTH-LOGIN-NO-ACCOUNT", email=email,
                           error="등록되지 않은 이메일입니다.")
    token = secrets.token_urlsafe(32)
    accounts.update(email, verify_token=token)
    return _login_page(email=email, notice=_send_verify_mail(email, acct.get("name", ""), token))


_OAUTH_PROVIDERS = ("kakao", "google", "naver", "apple")


@auth_bp.get("/<provider>/start")
def oauth_start(provider: str):
    """OAuth 시작 — state 생성 + 프로바이더로 리다이렉트."""
    if provider not in _OAUTH_PROVIDERS:
        return jsonify({"error": "지원하지 않는 프로바이더입니다."}), 400

    p = _get_provider(provider)
    if not p or not p.is_configured:
        flash(f"{provider} 로그인이 설정되지 않았습니다.", "warning")
        return redirect(url_for("auth.login"))

    state = secrets.token_urlsafe(24)
    session[f"oauth_state_{provider}"] = state
    # v87 계측: state 유실 갈래를 로그 두 줄 대조로 가른다(동작은 건드리지 않는다).
    #   state 값 자체는 **절대** 남기지 않는다 — 시크릿 평문 금지. 존재 여부·일치 여부만 본다.
    logger.info(
        "oauth_start provider=%s session_new=%s request_host=%s",
        provider, bool(getattr(session, "new", False)), request.host,
    )
    session[f"oauth_next_{provider}"] = _safe_next_url(
        request.args.get("next", ""),
        default=_oauth_default_next(provider),
    )
    # 자동 로그인 선호를 콜백까지 전달
    session[f"oauth_remember_{provider}"] = str(request.args.get("remember", "")).lower() in ("1", "on", "true", "yes")

    redirect_uri = _callback_uri(provider)
    auth_url = p.get_authorize_url(state=state, redirect_uri=redirect_uri)
    return redirect(auth_url)


@auth_bp.route("/<provider>/callback", methods=["GET", "POST"])
def oauth_callback(provider: str):
    """OAuth 콜백 — 코드 교환 + 사용자 생성/로그인.

    Apple은 response_mode=form_post로 콜백을 POST로 보낸다 → request.values(args+form)로 통일.
    """
    if provider not in _OAUTH_PROVIDERS:
        return jsonify({"error": "지원하지 않는 프로바이더입니다."}), 400

    # CSRF 방어: state 파라미터 검증 (GET=query, POST(form_post)=form)
    state_param = request.values.get("state", "")
    state_stored = session.pop(f"oauth_state_{provider}", "")
    state_equal = bool(state_param and state_stored
                       and secrets.compare_digest(state_param, state_stored))
    # v87 계측: '보안 오류'가 어느 갈래인지 로그 한 줄로 가른다(동작 불변 — 판정은 아래 기존 분기 그대로).
    #   cookie_header_present=false          → 쿠키가 아예 안 돌아옴(브라우저·도메인 갈래)
    #   쿠키 있고 session_has_state=false    → 세션 저장/백엔드 갈래
    #   둘 다 true인데 state_equal=false     → 이중 시작(탭 중복·재클릭) 갈래
    #   state 값 자체는 절대 로그하지 않는다(시크릿 평문 금지) — 존재·일치 여부만.
    try:
        _ref = request.referrer or ""
        _ref_host = _ref.split("//", 1)[-1].split("/", 1)[0] if "//" in _ref else ""
        logger.info(
            "oauth_callback provider=%s cookie_header_present=%s session_has_state=%s "
            "received_state_present=%s state_equal=%s request_host=%s referrer_host=%s",
            provider,
            bool(request.headers.get("Cookie")),
            bool(state_stored),
            bool(state_param),
            state_equal,
            request.host,
            _ref_host,
        )
    except Exception:   # 계측이 로그인 흐름을 절대 막지 않는다
        logger.exception("oauth_callback 계측 로그 실패(무시)")

    if not state_equal:
        flash("보안 오류가 발생했습니다. 다시 시도해주세요.", "auth_oauth")
        return redirect(url_for("auth.login"))

    code = request.values.get("code", "")
    if not code:
        error = request.values.get("error", "알 수 없는 오류")
        flash(f"로그인 취소 또는 오류: {error}", "auth_oauth")
        return redirect(url_for("auth.login"))

    next_url = session.pop(f"oauth_next_{provider}", _oauth_default_next(provider))

    p = _get_provider(provider)
    if not p:
        flash("프로바이더 오류", "auth_oauth")
        return redirect(url_for("auth.login"))

    try:
        token_data = p.exchange_code(code=code, redirect_uri=_callback_uri(provider))
        if "error" in token_data:
            flash("토큰 교환 실패: " + str(token_data.get("error", "")), "auth_oauth")
            return redirect(url_for("auth.login"))

        access_token = token_data.get("access_token", "")
        user_info = p.get_user_info(access_token)
        if "error" in user_info:
            flash("사용자 정보 조회 실패", "auth_oauth")
            return redirect(url_for("auth.login"))

        provider_user_id = user_info.get("provider_user_id", "")
        email = user_info.get("email", "")
        name = user_info.get("name", "") or (email.split("@")[0] if email else provider_user_id)
        avatar_url = user_info.get("avatar_url", "")

        from .user_store import get_store
        from .models import User
        store = get_store()

        # 기존 소셜 계정으로 찾기
        user = store.find_by_provider(provider, provider_user_id)

        if user is None and email:
            # 이메일로 찾기 (소셜 계정 연결)
            user = store.find_by_email(email)
            if user:
                store.link_social(user.user_id, {
                    "provider": provider,
                    "provider_user_id": provider_user_id,
                })

        # C-F19: **만들기 전에 정체성 표를 본다.** 실측(오너 2026-09-13 16:02): 구글로 들어왔더니
        #   「신규 셀러 가입」이 뜨고 새 user_id가 났다 — 데이터를 쥔 UUID는 따로였다.
        #   찾기가 실패할 수 있는 한, 만들기 앞에 **기억해 둔 표**가 있어야 한다.
        known_uid = ""
        if user is None and email:
            from .identity import register_login, resolve_user_id
            known_uid = resolve_user_id(provider, email)
            if known_uid:
                # 저장소 조회가 **터져도 로그인은 계속된다.** 표가 "누구인지"를 이미 알고 있으니,
                #   못 읽은 것은 그 신원으로 세우면 된다 — 여기서 예외가 나면 사람이 못 들어온다.
                try:
                    user = store.find_by_id(known_uid)
                except Exception as exc:
                    logger.warning("사용자 레코드 조회 실패(정체성으로 계속): %s", exc)
                    user = None
                if user is None:
                    # 사용자 저장소(시트)가 닿지 않아도 로그인은 된다 —
                    #   정체성 표가 "누구인지"를 알고 있으므로 그 신원으로 세션을 연다.
                    from .identity import profile as _idprof
                    prof = _idprof(known_uid)
                    user = User(user_id=known_uid, email=email,
                                name=prof.get("display_name") or name,
                                avatar_url=avatar_url, role="seller",
                                email_verified=True, active=True)
                register_login(provider, email, known_uid)

        if user is None:
            # 신규 가입
            role = _resolve_user_role(email, provider=provider, provider_user_id=provider_user_id)
            user = User.new(email=email, name=name, avatar_url=avatar_url, role=role)
            user.email_verified = True  # 소셜 검증된 이메일
            user.social_accounts = [{
                "provider": provider,
                "provider_user_id": provider_user_id,
                "linked_at": datetime.now(timezone.utc).isoformat(),
            }]
            store.create(user)

            # C-F19: 이 사람을 **표에 적는다** — 다음 로그인부터는 새로 만들지 않는다.
            from .identity import known_email as _known, register_login as _reg
            was_known = _known(email) if email else False
            if email:
                _reg(provider, email, user.user_id, display_name=name)

            # 텔레그램 알림 — **처음 보는 이메일일 때만**(같은 사람이 로그인할 때마다
            #   「신규 가입」이 오면 그 알림은 곧 아무 뜻도 없게 된다).
            if not was_known:
                try:
                    from src.notifications.telegram import send_telegram
                    provider_label = {"kakao": "카카오", "google": "구글", "naver": "네이버"}.get(provider, provider)
                    _async_notify(
                        send_telegram,
                        f"🆕 신규 셀러 가입\n이메일: {email}\n이름: {name}\n경로: {provider_label} 로그인",
                        urgency="info",
                    )
                except Exception:
                    pass

        role = _resolve_user_role(email, provider=provider, provider_user_id=provider_user_id)
        if not email:
            flash("이메일 동의가 없어 일반 셀러 권한으로 로그인됩니다.", "warning")
        if user.role != role:
            user.role = role
            store.update(user)

        remember = bool(session.pop(f"oauth_remember_{provider}", False))
        establish_session(user, role=role, remember=remember)

        store.update_last_login(user.user_id)
        popup_mode = provider == "kakao" and (
            os.getenv("KAKAO_OAUTH_POPUP_MODE", "0") == "1"
            or request.args.get("popup") == "1"
        )
        if popup_mode:
            return _popup_redirect_response(next_url)
        return redirect(next_url)

    except Exception as exc:
        logger.warning("oauth_callback 오류 (%s): %s", provider, exc)
        flash("로그인 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.get("/whoami")
def whoami():
    """현재 세션 디버그용. 로그인 상태/role/email 표시."""
    from .admin_resolver import is_admin_session
    admin_ok, admin_rule = is_admin_session(session)
    return jsonify({
        "logged_in": bool(session.get("user_id")),
        "user_id": session.get("user_id"),
        "user_email": session.get("user_email"),
        "user_role": session.get("user_role"),
        "user_name": session.get("user_name"),
        "admin_emails_configured": bool(os.getenv("ADMIN_EMAILS")),
        "is_admin": admin_ok,
        "admin_rule": admin_rule,
    })


@auth_bp.post("/logout")
def logout():
    """세션 종료."""
    session.clear()
    flash("로그아웃되었습니다.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.get("/logout")
def logout_get():
    """GET 로그아웃 (편의용)."""
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.get("/verify-email")
def verify_email():
    """이메일 인증 처리(AUTH-1: 비밀번호 계정 저장소 기준)."""
    from . import password_accounts as accounts
    token = request.args.get("token", "")
    if not token:
        return _login_page(status=400, error_code="AUTH-VERIFY-EMPTY", error="유효하지 않은 인증 링크입니다.")
    try:
        acct = accounts.by_token("verify", token)
    except accounts.StoreDown as exc:
        return _login_page(status=503, error_code="AUTH-STORE-DOWN",
                           error=f"계정 저장소에 연결하지 못했어요 — {_why(exc)}")
    if not acct:
        return _login_page(status=400, error_code="AUTH-VERIFY-INVALID",
                           error="유효하지 않거나 이미 쓴 인증 링크입니다.")
    accounts.update(acct["email"], email_verified=True, verify_token="")
    return _login_page(email=acct["email"], notice="이메일 인증이 완료되었습니다. 로그인해 주세요.")


@auth_bp.post("/forgot")
def forgot():
    """비밀번호 재설정 메일 발송."""
    from . import password_accounts as accounts
    email = request.form.get("email", "").strip().lower()
    if not email:
        return _login_page(status=400, error_code="AUTH-FORGOT-EMPTY", error="이메일을 입력해 주세요.")
    try:
        acct = accounts.find(email)
    except accounts.StoreDown as exc:
        return _login_page(status=503, error_code="AUTH-STORE-DOWN", email=email,
                           error=f"계정 저장소에 연결하지 못했어요 — {_why(exc)}")
    if not acct:
        return _login_page(status=404, error_code="AUTH-LOGIN-NO-ACCOUNT", email=email,
                           error="등록되지 않은 이메일입니다 — 먼저 가입해 주세요.")
    token = secrets.token_urlsafe(32)
    accounts.update(email, reset_token=token,
                    reset_token_exp=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    try:
        from src.notifications.email_resend import send_email
        reset_url = f"{os.getenv('APP_BASE_URL', 'https://kohganepercentiii.com')}/auth/reset?token={token}"
        sent = send_email(
            to=email,
            subject="[고가브릿지] 비밀번호 재설정",
            html=f"<p>비밀번호 재설정 링크입니다 (1시간 유효):</p>"
                 f"<p><a href='{reset_url}'>비밀번호 재설정하기</a></p>",
            text=f"비밀번호 재설정: {reset_url}",
        )
    except Exception as exc:
        logger.warning("[auth] 재설정 메일 예외: %s", exc)
        sent = False
    if not sent:
        return _login_page(status=503, error_code="AUTH-MAIL-OFF", email=email,
                           error="재설정 메일을 보내지 못했어요 — 메일 발송 설정이 꺼져 있거나 거절됐어요. "
                                 "운영자에게 이 코드를 알려 주세요.")
    return _login_page(email=email, notice="재설정 링크를 메일로 보냈어요(1시간 유효).")


@auth_bp.get("/reset")
def reset():
    """비밀번호 재설정 페이지."""
    token = request.args.get("token", "")
    return render_template("auth/reset.html", token=token)


@auth_bp.post("/reset")
def reset_post():
    """새 비밀번호 저장(AUTH-1: 비밀번호 계정 저장소 기준)."""
    from . import password_accounts as accounts
    token = request.form.get("token", "")
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")
    if not token:
        return _login_page(status=400, error_code="AUTH-RESET-EMPTY", error="유효하지 않은 요청입니다.")
    if len(password) < 8 or password != confirm:
        flash("비밀번호는 8자 이상이고 두 칸이 같아야 합니다.", "danger")
        return redirect(url_for("auth.reset", token=token))
    try:
        acct = accounts.by_token("reset", token)
    except accounts.StoreDown as exc:
        return _login_page(status=503, error_code="AUTH-STORE-DOWN",
                           error=f"계정 저장소에 연결하지 못했어요 — {_why(exc)}")
    if not acct:
        return _login_page(status=400, error_code="AUTH-RESET-INVALID", error="유효하지 않거나 이미 쓴 링크입니다.")
    exp = acct.get("reset_token_exp") or ""
    try:
        if exp and datetime.now(timezone.utc) > datetime.fromisoformat(str(exp).replace("Z", "+00:00")):
            return _login_page(status=400, error_code="AUTH-RESET-EXPIRED", email=acct["email"],
                               error="링크가 만료되었습니다(1시간) — 다시 요청해 주세요.")
    except ValueError:
        pass
    accounts.update(acct["email"], password_hash=_hash_password(password), reset_token="", reset_token_exp="")
    return _login_page(email=acct["email"], notice="비밀번호가 변경되었습니다. 로그인해 주세요.")
