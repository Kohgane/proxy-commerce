"""Bootstrap emergency admin login Blueprint."""
from __future__ import annotations

import hmac
import logging
import os
from urllib.parse import urlparse

from flask import Blueprint, flash, jsonify, redirect, request

from .views import _is_admin_email, establish_session

logger = logging.getLogger(__name__)

bootstrap_bp = Blueprint("bootstrap_auth", __name__)


def _trusted_redirect_target(raw_next_url: str, default: str = "/admin/diagnostics") -> str:
    candidate = (raw_next_url or "").strip()
    parsed = urlparse(candidate)
    if (
        not candidate
        or parsed.scheme
        or parsed.netloc
        or not candidate.startswith("/")
        or candidate.startswith("//")
        or "\\" in candidate
        or not (
            candidate == "/"
            or candidate.startswith("/seller/")
            or candidate.startswith("/admin/")
            or candidate.startswith("/auth/")
        )
    ):
        return default
    return candidate


@bootstrap_bp.get("/auth/bootstrap")
def bootstrap_login():
    """비상 admin 진입."""
    token = request.args.get("token", "")
    email = (request.args.get("email") or "").strip().lower()
    next_url = _trusted_redirect_target(request.args.get("next", ""), default="/admin/diagnostics")
    placeholder_patterns = [
        "<TOKEN>",
        "<ADMIN_BOOTSTRAP_TOKEN>",
        "your-token",
        "ADMIN_BOOTSTRAP_TOKEN",
        "REPLACE",
        "여기에",
    ]

    if any(p in token for p in placeholder_patterns):
        return (
            jsonify(
                {
                    "error": "토큰 자리에 placeholder 값이 들어있습니다.",
                    "hint": "Render 환경변수 ADMIN_BOOTSTRAP_TOKEN의 실제 값으로 교체하세요.",
                    "received_token_preview": token[:20] + "..." if len(token) > 20 else token,
                }
            ),
            400,
        )

    if token.startswith("/auth/") or token.startswith("https://"):
        return (
            jsonify(
                {
                    "error": "토큰에 URL 일부가 포함되어 있습니다 (이중 입력).",
                    "hint": "토큰 값만 깔끔히 입력하세요. 새 탭에서 다시 시도하세요.",
                }
            ),
            400,
        )

    expected = os.getenv("ADMIN_BOOTSTRAP_TOKEN", "")
    if not expected:
        return jsonify({"error": "ADMIN_BOOTSTRAP_TOKEN 환경변수 미설정. 운영자 전용 기능."}), 503

    if not hmac.compare_digest(token, expected):
        logger.warning("Bootstrap 토큰 불일치 시도: ip=%s email=%s", request.remote_addr, email)
        return jsonify({"error": "유효하지 않은 토큰"}), 401

    if not _is_admin_email(email):
        return (
            jsonify(
                {
                    "error": "이메일이 ADMIN_EMAILS에 없습니다.",
                    "hint": "ADMIN_EMAILS 환경변수에 추가 후 재시도",
                }
            ),
            403,
        )

    try:
        from src.auth.user_store import set_role, upsert_by_email

        user = upsert_by_email(
            email=email,
            provider="bootstrap",
            provider_id=email,
            name=email.split("@")[0],
        )
        user.role = "admin"
        set_role(user.user_id, "admin")
        establish_session(user, role="admin")
        logger.info("Bootstrap 로그인 성공: %s", email)
        flash(f"비상 admin 로그인 성공: {email}", "success")
        return redirect(next_url)
    except Exception as exc:
        logger.warning("Bootstrap 로그인 실패: %s", exc)
        return jsonify({"error": "비상 로그인 처리 중 오류가 발생했습니다."}), 500
