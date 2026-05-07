"""운영자 비상 진입용 diagnostic token."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, redirect, request, session

bp = Blueprint("diagnostic_token", __name__)
logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_FILE = Path(os.getenv("DIAGNOSTIC_TOKEN_PATH", "data/diagnostic_tokens.jsonl"))
_FILE.parent.mkdir(parents=True, exist_ok=True)
TTL_SECONDS = 600


def _admin_emails() -> list[str]:
    return [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]


@bp.get("/auth/diagnostic-token/issue")
def issue_token():
    admin_emails = _admin_emails()
    if not admin_emails:
        return jsonify({"error": "ADMIN_EMAILS 환경변수 미설정"}), 503

    raw = secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = int(time.time()) + TTL_SECONDS
    record = {
        "token_hash": token_hash,
        "expires_at": expires_at,
        "used": False,
        "issued_at": datetime.now(tz=timezone.utc).isoformat(),
        "issuer_ip": request.remote_addr,
    }
    with _LOCK:
        with _FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    base_url = os.getenv("BASE_URL", "https://kohganepercentiii.com").rstrip("/")
    redeem_url = f"{base_url}/auth/diagnostic-token/redeem?token={raw}"
    logger.warning("=" * 60)
    logger.warning("DIAGNOSTIC TOKEN 발급됨 (10분 유효, 1회용)")
    logger.warning("URL: %s", redeem_url)
    logger.warning("발급 IP: %s", request.remote_addr)
    logger.warning("=" * 60)

    return jsonify(
        {
            "ok": True,
            "hint": "Render 대시보드 로그에서 DIAGNOSTIC TOKEN URL을 확인하세요.",
            "ttl_seconds": TTL_SECONDS,
        }
    )


@bp.get("/auth/diagnostic-token/redeem")
def redeem_token():
    admin_emails = _admin_emails()
    if not admin_emails:
        return jsonify({"error": "ADMIN_EMAILS 환경변수 미설정"}), 503

    raw = request.args.get("token", "")
    if not raw:
        return jsonify({"error": "토큰 누락"}), 400

    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    now = int(time.time())
    records: list[dict] = []
    matched = False
    with _LOCK:
        if _FILE.exists():
            with _FILE.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw_line = line.strip()
                    if not raw_line:
                        continue
                    try:
                        row = json.loads(raw_line)
                    except Exception:
                        continue
                    is_match = (
                        row.get("token_hash") == token_hash
                        and not row.get("used")
                        and int(row.get("expires_at", 0)) > now
                    )
                    if is_match:
                        row["used"] = True
                        matched = True
                    records.append(row)

    if not matched:
        return jsonify({"error": "토큰을 찾을 수 없거나 만료/사용됨"}), 401

    with _LOCK:
        with _FILE.open("w", encoding="utf-8") as handle:
            for row in records:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    primary_admin = admin_emails[0]
    try:
        from src.auth.user_store import set_role, upsert_by_email

        user = upsert_by_email(
            email=primary_admin,
            provider="diagnostic",
            provider_id=primary_admin,
            name=primary_admin.split("@")[0],
        )
        set_role(user.user_id, "admin")
        session["user_id"] = user.user_id
        session["user_email"] = primary_admin
        session["user_role"] = "admin"
        session["user_name"] = user.name or primary_admin
    except Exception as exc:
        logger.error("diagnostic 세션 생성 실패: %s", exc)
        session["user_id"] = "diagnostic-admin"
        session["user_email"] = primary_admin
        session["user_role"] = "admin"
        session["user_name"] = "Diagnostic Admin"

    logger.info("Diagnostic 토큰 redeem 성공: %s", primary_admin)
    return redirect("/admin/diagnostics")
