"""src/auth/admin_resolver.py — 통일된 admin role 부여 메커니즘 (Phase 142).

다음 중 하나라도 해당하면 admin:
  1. user.role == "admin" (DB 저장)
  2. user.email in ADMIN_EMAILS (env, 콤마 구분)
  3. kakao provider_user_id in ADMIN_KAKAO_IDS (env)
  4. google provider_user_id in ADMIN_GOOGLE_SUBS (env)
  5. naver provider_user_id in ADMIN_NAVER_IDS (env)
  6. user.email == ADMIN_BOOTSTRAP_EMAIL (Phase 136 잔존)
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from .models import User

logger = logging.getLogger(__name__)


def _env_list(env_key: str) -> list:
    """환경변수에서 콤마 구분 목록 반환 (소문자, 공백 제거)."""
    raw = os.getenv(env_key, "")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def is_admin(user: "User") -> Tuple[bool, str]:
    """사용자가 admin인지 판단한다.

    Returns:
        (bool, rule) — rule은 어떤 규칙으로 통과했는지 (디버그용).
    """
    if user is None:
        return False, ""

    # 1. DB 저장 역할
    if getattr(user, "role", "") == "admin":
        return True, "db_role"

    email = (getattr(user, "email", "") or "").strip().lower()

    # 2. ADMIN_EMAILS 환경변수
    if email and email in _env_list("ADMIN_EMAILS"):
        return True, "ADMIN_EMAILS"

    # 3–5. 소셜 계정 ID 체크
    social_accounts = getattr(user, "social_accounts", []) or []
    for account in social_accounts:
        provider = account.get("provider", "")
        pid = (account.get("provider_user_id", "") or "").strip().lower()
        if not pid:
            continue
        kakao_ids = _env_list("ADMIN_KAKAO_IDS")
        if provider == "kakao" and kakao_ids and pid in kakao_ids:
            return True, "ADMIN_KAKAO_IDS"
        google_subs = _env_list("ADMIN_GOOGLE_SUBS")
        if provider == "google" and google_subs and pid in google_subs:
            return True, "ADMIN_GOOGLE_SUBS"
        naver_ids = _env_list("ADMIN_NAVER_IDS")
        if provider == "naver" and naver_ids and pid in naver_ids:
            return True, "ADMIN_NAVER_IDS"

    # 6. ADMIN_BOOTSTRAP_EMAIL (Phase 136 잔존 호환)
    bootstrap_email = (os.getenv("ADMIN_BOOTSTRAP_EMAIL", "") or "").strip().lower()
    if email and bootstrap_email and email == bootstrap_email:
        return True, "ADMIN_BOOTSTRAP_EMAIL"

    return False, ""


def is_admin_session(sess: dict) -> Tuple[bool, str]:
    """Flask 세션에서 admin 여부를 판단한다.

    DB 조회 없이 세션 + env 기반으로 빠르게 판단.
    세션 user_role이 "admin"이면 True.
    아니더라도 세션 이메일이 ADMIN_EMAILS에 있으면 True.
    """
    user_id = sess.get("user_id")
    if not user_id:
        return False, ""

    user_role = sess.get("user_role", "")
    if user_role == "admin":
        return True, "session_role"

    # 세션 이메일로 ADMIN_EMAILS 체크 (세션 role이 outdated일 수 있음)
    email = (sess.get("user_email", "") or "").strip().lower()
    if email and email in _env_list("ADMIN_EMAILS"):
        return True, "ADMIN_EMAILS"

    # F30-0: **판정 기준은 정본 user_id다** — 이메일 문자열이 아니다.
    #
    #   이 함수는 원래 세션 role과 `ADMIN_EMAILS` 둘만 봤다(위 두 줄). `ADMIN_EMAILS`가
    #   설정돼 있지 않으면 오너가 자기 화면(저장소 진단·정체성 감사)에 **못 들어간다** —
    #   게이트를 세게 잠근 F29가 그 위험을 만들었다.
    #
    #   F19가 이미 「어느 로그인이 누구인가」를 **정본 user_id 하나로** 묶어 뒀다
    #   (hanmail이든 구글이든 같은 사람). 그 결론을 여기서 쓴다 — 정체성 판정을 두 벌로
    #   만들지 않는다. 이메일은 **판정 기준이 아니라 정체성 표를 찾는 열쇠**로만 쓴다.
    if _user_id_is_admin(str(user_id).strip()):
        return True, "ADMIN_USER_IDS"
    if email:
        canonical = _canonical_of(email)
        if canonical and _user_id_is_admin(canonical):
            return True, "ADMIN_USER_IDS(정체성)"

    return False, ""


def _canonical_of(email: str) -> str:
    """이 로그인 이메일의 **정본 user_id**. 모르면 빈 문자열.

    ① 정체성 표(`user_identities`)가 정본이다.
    ② 표가 대답 못 하면(PG 미연결·부팅 직후) **그 표의 씨앗**을 본다 —
       `identity.OWNER_LOGINS`가 곧 부팅 때 표에 등록되는 두 줄이다.

    **이메일이 권한을 주는 게 아니다.** 이메일은 표를 찾는 열쇠이고, 판정은 나온 id로 한다.
    """
    mail = str(email or "").strip().lower()
    if not mail:
        return ""
    try:
        from src.auth.identity import OWNER_LOGINS, OWNER_USER_ID, resolve_user_id
    except Exception as exc:
        logger.debug("[관리자 판정] 정체성 모듈 없음: %s", exc)
        return ""
    try:
        hit = resolve_user_id("", mail)
        if hit:
            return hit
    except Exception as exc:
        logger.debug("[관리자 판정] 정체성 표 조회 실패: %s", exc)
    if mail in {e for _p, e in OWNER_LOGINS if e}:
        return OWNER_USER_ID
    return ""


def admin_user_ids() -> set:
    """관리자 **user_id** 목록.

    `ADMIN_USER_IDS`(콤마 구분) + 정본 오너 id. `user_identities.is_admin` 컬럼도,
    `ADMIN_USER_IDS` env도 **코드에 없던 것**이라 env 쪽을 골랐다 —
    스키마 변경·마이그레이션 없이 지금 배포에서 바로 듣고, 기본값이 정본 id를 포함한다.
    """
    ids = set(_env_list("ADMIN_USER_IDS"))
    try:
        from src.auth.identity import OWNER_USER_ID
        if OWNER_USER_ID:
            ids.add(OWNER_USER_ID.strip().lower())
    except Exception:
        pass
    return {i for i in ids if i}


def _user_id_is_admin(user_id: str) -> bool:
    uid = str(user_id or "").strip().lower()
    return bool(uid) and uid in admin_user_ids()


def resolve_role_for_login(
    email: str,
    provider: str = "",
    provider_user_id: str = "",
) -> str:
    """로그인 시 역할을 결정한다.

    Args:
        email: 사용자 이메일 (없을 수 있음)
        provider: OAuth 제공자 ("kakao" / "google" / "naver" / "")
        provider_user_id: 제공자 고유 ID

    Returns:
        "admin" 또는 "seller"
    """
    email_lc = (email or "").strip().lower()
    pid_lc = (provider_user_id or "").strip().lower()

    if email_lc and email_lc in _env_list("ADMIN_EMAILS"):
        logger.info("ADMIN_EMAILS 매칭 — admin role 부여: %s", email_lc)
        return "admin"

    if provider == "kakao" and pid_lc and pid_lc in _env_list("ADMIN_KAKAO_IDS"):
        logger.info("ADMIN_KAKAO_IDS 매칭 — admin role 부여: %s", pid_lc)
        return "admin"

    if provider == "google" and pid_lc and pid_lc in _env_list("ADMIN_GOOGLE_SUBS"):
        logger.info("ADMIN_GOOGLE_SUBS 매칭 — admin role 부여: %s", pid_lc)
        return "admin"

    if provider == "naver" and pid_lc and pid_lc in _env_list("ADMIN_NAVER_IDS"):
        logger.info("ADMIN_NAVER_IDS 매칭 — admin role 부여: %s", pid_lc)
        return "admin"

    # Phase 136 잔존 호환
    bootstrap_email = (os.getenv("ADMIN_BOOTSTRAP_EMAIL", "") or "").strip().lower()
    if email_lc and bootstrap_email and email_lc == bootstrap_email:
        logger.info("ADMIN_BOOTSTRAP_EMAIL 매칭 — admin role 부여: %s", email_lc)
        return "admin"

    return "seller"
