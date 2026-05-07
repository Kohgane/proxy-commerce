"""Bootstrap emergency admin login Blueprint."""
from __future__ import annotations

import hmac
import logging
import os

from flask import Blueprint, flash, jsonify, redirect, request

from .views import _is_admin_email, _safe_next_url, establish_session

logger = logging.getLogger(__name__)

bootstrap_bp = Blueprint("bootstrap_auth", __name__)


@bootstrap_bp.get("/auth/bootstrap")
def bootstrap_login():
    """비상 admin 진입."""
    token = request.args.get("token", "")
    email = (request.args.get("email") or "").strip().lower()
    next_url = _safe_next_url(request.args.get("next", ""), default="/admin/diagnostics")

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
