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

    return False, ""


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
