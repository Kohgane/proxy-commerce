"""운영자 비상 진입용 diagnostic token."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, redirect, render_template, request, session

bp = Blueprint("diagnostic_token", __name__)
logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_FILE = Path(os.getenv("DIAGNOSTIC_TOKEN_PATH", "data/diagnostic_tokens.jsonl"))
_FILE.parent.mkdir(parents=True, exist_ok=True)
TTL_SECONDS = 600
_SEPARATOR = "=" * 70


def _admin_emails() -> list[str]:
    return [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]


def _load_records() -> list[dict]:
    if not _FILE.exists():
        return []
    rows: list[dict] = []
    with _FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw_line = line.strip()
            if not raw_line:
                continue
            try:
                rows.append(json.loads(raw_line))
            except Exception:
                continue
    return rows


def _write_records(records: list[dict]) -> None:
    with _FILE.open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def token_status() -> dict:
    now = int(time.time())
    with _LOCK:
        rows = _load_records()
    active = [r for r in rows if (not r.get("used")) and int(r.get("expires_at", 0) or 0) > now]
    latest = max((str(r.get("issued_at", "")) for r in rows if r.get("issued_at")), default=None)
    return {"active_count": len(active), "latest_issued_at": latest}


def expire_all_tokens() -> int:
    updated = 0
    with _LOCK:
        rows = _load_records()
        for row in rows:
            if not row.get("used"):
                row["used"] = True
                updated += 1
            row["expires_at"] = 0
        _write_records(rows)
    return updated


def _notify_telegram_on_issue(ip: str | None, issued_at: str) -> None:
    try:
        from src.notifications.telegram import send_telegram
        kst = datetime.fromisoformat(issued_at).astimezone(ZoneInfo("Asia/Seoul"))
        message = (
            "🆘 Diagnostic Token 발급됨\n"
            f"- IP: {ip or '-'}\n"
            f"- 시각: {kst.strftime('%Y-%m-%d %H:%M KST')}\n"
            "- 본인이 발급하지 않았다면 즉시 ADMIN_BOOTSTRAP_TOKEN/DIAGNOSTIC_REVEAL 환경변수 회전"
        )
        send_telegram(message, urgency="warning")
    except Exception as exc:
        logger.debug("diagnostic token 텔레그램 알림 스킵: %s", exc)


@bp.get("/auth/diagnostic-token/issue")
def issue_token():
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

    sys.stdout.write("\n" + _SEPARATOR + "\n")
    sys.stdout.write(f"🆘 DIAGNOSTIC TOKEN URL: {redeem_url}\n")
    sys.stdout.write(_SEPARATOR + "\n\n")
    sys.stdout.flush()

    logger.warning(_SEPARATOR)
    logger.warning("🆘 DIAGNOSTIC TOKEN 발급됨 (10분 유효, 1회용)")
    logger.warning("URL: %s", redeem_url)
    logger.warning("발급 IP: %s", request.remote_addr)
    logger.warning(_SEPARATOR)

    _notify_telegram_on_issue(ip=request.remote_addr, issued_at=record["issued_at"])

    admin_emails_set = bool(os.getenv("ADMIN_EMAILS", "").strip())
    reveal_env = os.getenv("DIAGNOSTIC_REVEAL", "0") == "1"

    can_reveal = reveal_env and admin_emails_set
    if request.args.get("format") != "json" and can_reveal:
        return render_template(
            "auth/diagnostic_token_issued.html",
            redeem_url=redeem_url,
            ttl_minutes=TTL_SECONDS // 60,
            issuer_ip=request.remote_addr,
        )

    payload = {
        "ok": True,
        "hint": (
            "Render Logs 탭에서 'DIAGNOSTIC TOKEN' 검색 → URL 복사. "
            "또는 ?reveal_safe=1&format=html 쿼리 추가 시 화면 표시 "
            "(ADMIN_EMAILS 설정 + DIAGNOSTIC_REVEAL=1 환경변수 필요)."
        ),
        "ttl_seconds": TTL_SECONDS,
        "issued_at": record["issued_at"],
        "log_keyword": "DIAGNOSTIC TOKEN",
    }
    if can_reveal:
        payload["redeem_url"] = redeem_url
    return jsonify(payload)


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
        for row in _load_records():
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
        _write_records(records)

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
