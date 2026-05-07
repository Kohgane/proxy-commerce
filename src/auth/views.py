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
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional
from urllib.parse import urlparse

from flask import (
    Blueprint,
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


def _resolve_user_role(email: str) -> str:
    """ADMIN_EMAILS 매칭 시 admin, 그 외 seller."""
    if email and _is_admin_email(email):
        logger.info("ADMIN_EMAILS 매칭 — admin role 부여: %s", email)
        return "admin"
    return "seller"


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
        parsed = urlparse(next_url)
        # scheme 또는 netloc가 있으면 외부 URL → 기본값 반환
        if parsed.scheme or parsed.netloc:
            return default
        # 경로만 있는 경우 허용 (상대 경로)
        return next_url
    except Exception:
        return default


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
    except Exception as exc:
        logger.warning("프로바이더 로드 실패 (%s): %s", provider, exc)
    return None


def _callback_uri(provider: str) -> str:
    """OAuth 콜백 URI 생성."""
    base = os.getenv("APP_BASE_URL", "https://kohganepercentiii.com")
    return f"{base}/auth/{provider}/callback"


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------

@auth_bp.get("/login")
def login():
    """로그인 페이지."""
    if session.get("user_id"):
        return redirect("/seller/dashboard")
    next_url = _safe_next_url(request.args.get("next", ""))
    kakao = _get_provider("kakao")
    google = _get_provider("google")
    naver = _get_provider("naver")
    return render_template(
        "auth/login.html",
        next_url=next_url,
        kakao_active=kakao.is_configured if kakao else False,
        google_active=google.is_configured if google else False,
        naver_active=naver.is_configured if naver else False,
    )


@auth_bp.get("/signup")
def signup():
    """회원가입 페이지."""
    if session.get("user_id"):
        return redirect("/seller/dashboard")
    kakao = _get_provider("kakao")
    google = _get_provider("google")
    naver = _get_provider("naver")
    return render_template(
        "auth/signup.html",
        kakao_active=kakao.is_configured if kakao else False,
        google_active=google.is_configured if google else False,
        naver_active=naver.is_configured if naver else False,
    )


@auth_bp.post("/signup")
def signup_post():
    """이메일 + 비밀번호 회원가입 처리."""
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    name = request.form.get("name", "").strip() or email.split("@")[0]

    if not email or not password:
        flash("이메일과 비밀번호를 입력해주세요.", "danger")
        return redirect(url_for("auth.signup"))

    if len(password) < 8:
        flash("비밀번호는 8자 이상이어야 합니다.", "danger")
        return redirect(url_for("auth.signup"))

    try:
        from .user_store import get_store
        from .models import User
        store = get_store()

        existing = store.find_by_email(email)
        if existing:
            flash("이미 등록된 이메일입니다. 로그인하세요.", "warning")
            return redirect(url_for("auth.login"))

        role = "admin" if _is_admin_email(email) else "seller"
        user = User.new(email=email, name=name, role=role)
        user.password_hash = _hash_password(password)

        # 이메일 인증 토큰
        verify_token = secrets.token_urlsafe(32)
        user.reset_token = verify_token  # 인증 전까지 재사용
        user.reset_token_exp = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

        store.create(user)

        # 인증 메일 발송
        try:
            from src.notifications.email_resend import send_email
            verify_url = f"{os.getenv('APP_BASE_URL', 'https://kohganepercentiii.com')}/auth/verify-email?token={verify_token}"
            send_email(
                to=email,
                subject="[코가네 퍼센티] 이메일 인증",
                html=f"<p>안녕하세요, {name}님!</p>"
                     f"<p>아래 링크를 클릭하여 이메일을 인증해주세요:</p>"
                     f"<p><a href='{verify_url}'>이메일 인증하기</a></p>",
                text=f"이메일 인증: {verify_url}",
            )
        except Exception as mail_exc:
            logger.warning("인증 메일 발송 실패 (가입은 완료됨): %s", mail_exc)

        # 텔레그램 알림
        try:
            from src.notifications.telegram import send_telegram
            send_telegram(
                f"🆕 신규 셀러 가입\n이메일: {email}\n이름: {name}\n경로: 이메일 가입",
                urgency="info",
            )
        except Exception:
            pass

        flash("가입이 완료되었습니다. 이메일 인증 후 로그인해주세요.", "success")
        return redirect(url_for("auth.login"))
    except Exception as exc:
        logger.warning("signup_post 오류: %s", exc)
        flash("가입 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("auth.signup"))


@auth_bp.post("/login")
def login_post():
    """이메일 + 비밀번호 로그인 처리."""
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    next_url = _safe_next_url(request.form.get("next", ""))

    if not email or not password:
        flash("이메일과 비밀번호를 입력해주세요.", "danger")
        return redirect(url_for("auth.login"))

    try:
        from .user_store import get_store
        store = get_store()
        user = store.find_by_email(email)

        if not user or not _verify_password(password, user.password_hash):
            flash("이메일 또는 비밀번호가 올바르지 않습니다.", "danger")
            return redirect(url_for("auth.login"))

        session["user_id"] = user.user_id
        session["user_email"] = user.email
        session["user_name"] = user.name
        session["user_role"] = user.role
        session.permanent = True

        store.update_last_login(user.user_id)
        return redirect(next_url)
    except Exception as exc:
        logger.warning("login_post 오류: %s", exc)
        flash("로그인 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.get("/<provider>/start")
def oauth_start(provider: str):
    """OAuth 시작 — state 생성 + 프로바이더로 리다이렉트."""
    if provider not in ("kakao", "google", "naver"):
        return jsonify({"error": "지원하지 않는 프로바이더입니다."}), 400

    p = _get_provider(provider)
    if not p or not p.is_configured:
        flash(f"{provider} 로그인이 설정되지 않았습니다.", "warning")
        return redirect(url_for("auth.login"))

    state = secrets.token_urlsafe(24)
    session[f"oauth_state_{provider}"] = state
    session[f"oauth_next_{provider}"] = _safe_next_url(request.args.get("next", ""))

    redirect_uri = _callback_uri(provider)
    auth_url = p.get_authorize_url(state=state, redirect_uri=redirect_uri)
    return redirect(auth_url)


@auth_bp.get("/<provider>/callback")
def oauth_callback(provider: str):
    """OAuth 콜백 — 코드 교환 + 사용자 생성/로그인."""
    if provider not in ("kakao", "google", "naver"):
        return jsonify({"error": "지원하지 않는 프로바이더입니다."}), 400

    # CSRF 방어: state 파라미터 검증
    state_param = request.args.get("state", "")
    state_stored = session.pop(f"oauth_state_{provider}", "")
    if not state_param or not secrets.compare_digest(state_param, state_stored):
        flash("보안 오류가 발생했습니다. 다시 시도해주세요.", "danger")
        return redirect(url_for("auth.login"))

    code = request.args.get("code", "")
    if not code:
        error = request.args.get("error", "알 수 없는 오류")
        flash(f"로그인 취소 또는 오류: {error}", "warning")
        return redirect(url_for("auth.login"))

    next_url = session.pop(f"oauth_next_{provider}", "/seller/dashboard")

    p = _get_provider(provider)
    if not p:
        flash("프로바이더 오류", "danger")
        return redirect(url_for("auth.login"))

    try:
        token_data = p.exchange_code(code=code, redirect_uri=_callback_uri(provider))
        if "error" in token_data:
            flash("토큰 교환 실패: " + str(token_data.get("error", "")), "danger")
            return redirect(url_for("auth.login"))

        access_token = token_data.get("access_token", "")
        user_info = p.get_user_info(access_token)
        if "error" in user_info:
            flash("사용자 정보 조회 실패", "danger")
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

        if user is None:
            # 신규 가입
            role = _resolve_user_role(email)
            user = User.new(email=email, name=name, avatar_url=avatar_url, role=role)
            user.email_verified = True  # 소셜 검증된 이메일
            user.social_accounts = [{
                "provider": provider,
                "provider_user_id": provider_user_id,
                "linked_at": datetime.now(timezone.utc).isoformat(),
            }]
            store.create(user)

            # 텔레그램 알림
            try:
                from src.notifications.telegram import send_telegram
                provider_label = {"kakao": "카카오", "google": "구글", "naver": "네이버"}.get(provider, provider)
                send_telegram(
                    f"🆕 신규 셀러 가입\n이메일: {email}\n이름: {name}\n경로: {provider_label} 로그인",
                    urgency="info",
                )
            except Exception:
                pass

        role = _resolve_user_role(email)
        if not email:
            flash("이메일 동의가 없어 일반 셀러 권한으로 로그인됩니다.", "warning")
        if user.role != role:
            user.role = role
            store.update(user)

        session["user_id"] = user.user_id
        session["user_email"] = user.email
        session["user_name"] = user.name
        session["user_role"] = role
        session.permanent = True

        store.update_last_login(user.user_id)
        return redirect(next_url)

    except Exception as exc:
        logger.warning("oauth_callback 오류 (%s): %s", provider, exc)
        flash("로그인 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.get("/whoami")
def whoami():
    """현재 세션 디버그용. 로그인 상태/role/email 표시."""
    return jsonify({
        "logged_in": bool(session.get("user_id")),
        "user_id": session.get("user_id"),
        "user_email": session.get("user_email"),
        "user_role": session.get("user_role"),
        "user_name": session.get("user_name"),
        "admin_emails_configured": bool(os.getenv("ADMIN_EMAILS")),
        "is_admin": session.get("user_role") == "admin",
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
    """이메일 인증 처리."""
    token = request.args.get("token", "")
    if not token:
        flash("유효하지 않은 인증 링크입니다.", "danger")
        return redirect(url_for("auth.login"))

    try:
        from .user_store import get_store
        store = get_store()
        user = store.find_by_reset_token(token)

        if not user:
            flash("유효하지 않거나 만료된 인증 링크입니다.", "danger")
            return redirect(url_for("auth.login"))

        user.email_verified = True
        user.reset_token = ""
        user.reset_token_exp = ""
        store.update(user)

        flash("이메일 인증이 완료되었습니다. 로그인해주세요.", "success")
        return redirect(url_for("auth.login"))
    except Exception as exc:
        logger.warning("verify_email 오류: %s", exc)
        flash("이메일 인증 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.post("/forgot")
def forgot():
    """비밀번호 재설정 메일 발송."""
    email = request.form.get("email", "").strip().lower()
    if not email:
        flash("이메일을 입력해주세요.", "danger")
        return redirect(url_for("auth.login"))

    try:
        from .user_store import get_store
        from src.notifications.email_resend import send_email
        store = get_store()
        user = store.find_by_email(email)

        if user:
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            user.reset_token_exp = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            store.update(user)

            reset_url = f"{os.getenv('APP_BASE_URL', 'https://kohganepercentiii.com')}/auth/reset?token={token}"
            send_email(
                to=email,
                subject="[코가네 퍼센티] 비밀번호 재설정",
                html=f"<p>비밀번호 재설정 링크입니다 (1시간 유효):</p>"
                     f"<p><a href='{reset_url}'>비밀번호 재설정하기</a></p>",
                text=f"비밀번호 재설정: {reset_url}",
            )

        # 사용자 존재 여부와 무관하게 동일한 메시지 (보안)
        flash("이메일이 등록되어 있다면 재설정 링크를 발송했습니다.", "info")
    except Exception as exc:
        logger.warning("forgot 오류: %s", exc)
        flash("요청 처리 중 오류가 발생했습니다.", "danger")

    return redirect(url_for("auth.login"))


@auth_bp.get("/reset")
def reset():
    """비밀번호 재설정 페이지."""
    token = request.args.get("token", "")
    return render_template("auth/reset.html", token=token)


@auth_bp.post("/reset")
def reset_post():
    """새 비밀번호 저장."""
    token = request.form.get("token", "")
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    if not token:
        flash("유효하지 않은 요청입니다.", "danger")
        return redirect(url_for("auth.login"))

    if len(password) < 8:
        flash("비밀번호는 8자 이상이어야 합니다.", "danger")
        return redirect(url_for("auth.reset", token=token))

    if password != confirm:
        flash("비밀번호가 일치하지 않습니다.", "danger")
        return redirect(url_for("auth.reset", token=token))

    try:
        from .user_store import get_store
        store = get_store()
        user = store.find_by_reset_token(token)

        if not user:
            flash("유효하지 않거나 만료된 링크입니다.", "danger")
            return redirect(url_for("auth.login"))

        # 토큰 만료 확인
        exp_str = user.reset_token_exp
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                now_aware = datetime.now(timezone.utc)
                if now_aware > exp_dt:
                    flash("링크가 만료되었습니다. 다시 요청해주세요.", "danger")
                    return redirect(url_for("auth.login"))
            except Exception:
                pass

        user.password_hash = _hash_password(password)
        user.reset_token = ""
        user.reset_token_exp = ""
        store.update(user)

        flash("비밀번호가 변경되었습니다. 로그인해주세요.", "success")
        return redirect(url_for("auth.login"))
    except Exception as exc:
        logger.warning("reset_post 오류: %s", exc)
        flash("비밀번호 변경 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("auth.login"))
