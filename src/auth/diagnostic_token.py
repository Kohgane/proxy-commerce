"""운영자 비상 진입용 diagnostic token (HMAC 서명, stateless)."""
from __future__ import annotations

import base64
import hmac
import hashlib
import json
import logging
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, redirect, render_template, request, session

bp = Blueprint("diagnostic_token", __name__)
logger = logging.getLogger(__name__)

TTL_SECONDS = 600
_SEPARATOR = "=" * 70
_HOUR_SECONDS = 3600

_used_nonces: dict[str, int] = {}
_issued_nonces: dict[str, dict] = {}
_issue_events: list[int] = []
_redeem_events: list[int] = []


def _admin_emails() -> list[str]:
    return [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def _signing_key() -> bytes:
    """서명 키 = SECRET_KEY + DIAGNOSTIC_SALT."""
    base = os.getenv("SECRET_KEY") or os.getenv("ADMIN_BOOTSTRAP_TOKEN") or ""
    salt = os.getenv("DIAGNOSTIC_SALT", "diagnostic-token-v1")
    if not base:
        return b""
    return hashlib.sha256((base + salt).encode("utf-8")).digest()


def _sign_payload(payload: dict) -> str:
    key = _signing_key()
    if not key:
        raise RuntimeError("SECRET_KEY 미설정")
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(key, body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(sig)}"


def _verify_token(token: str) -> dict:
    if "." not in token:
        raise ValueError("형식 오류")
    body, sig = token.rsplit(".", 1)
    key = _signing_key()
    if not key:
        raise RuntimeError("서명 키 미설정")
    expected = hmac.new(key, body.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url_decode(sig), expected):
        raise ValueError("서명 불일치")
    payload = json.loads(_b64url_decode(body))
    if int(payload.get("exp", 0) or 0) < int(time.time()):
        raise ValueError("만료됨")
    nonce = str(payload.get("nonce") or "")
    if not nonce:
        raise ValueError("nonce 누락")
    return payload


def _prune(now: int | None = None) -> int:
    now = now or int(time.time())
    for nonce, exp in list(_used_nonces.items()):
        if exp < now:
            _used_nonces.pop(nonce, None)
    for nonce, meta in list(_issued_nonces.items()):
        if int(meta.get("exp", 0) or 0) < now:
            _issued_nonces.pop(nonce, None)

    cutoff = now - _HOUR_SECONDS
    while _issue_events and _issue_events[0] < cutoff:
        _issue_events.pop(0)
    while _redeem_events and _redeem_events[0] < cutoff:
        _redeem_events.pop(0)
    return cutoff


def _record_event(events: list[int], ts: int | None = None) -> None:
    now = ts or int(time.time())
    events.append(now)
    _prune(now)


def _is_used(nonce: str) -> bool:
    _prune()
    return nonce in _used_nonces


def _mark_used(nonce: str, exp: int) -> None:
    _used_nonces[nonce] = int(exp)


def token_status() -> dict:
    now = int(time.time())
    _prune(now)
    active_count = 0
    latest_issued_at = None
    for nonce, meta in _issued_nonces.items():
        if nonce in _used_nonces:
            continue
        exp = int(meta.get("exp", 0) or 0)
        if exp <= now:
            continue
        active_count += 1
        issued_at = str(meta.get("issued_at") or "")
        if issued_at and (latest_issued_at is None or issued_at > latest_issued_at):
            latest_issued_at = issued_at
    return {"active_count": active_count, "latest_issued_at": latest_issued_at}


def expire_all_tokens() -> int:
    stats = token_status()
    _issued_nonces.clear()
    _used_nonces.clear()
    _issue_events.clear()
    _redeem_events.clear()
    return int(stats.get("active_count", 0) or 0)


def runtime_stats() -> dict:
    _prune()
    return {
        "worker_pid": os.getpid(),
        "web_concurrency": os.getenv("WEB_CONCURRENCY", ""),
        "nonce_cache_size": len(_used_nonces),
        "issued_last_hour": len(_issue_events),
        "redeemed_last_hour": len(_redeem_events),
    }


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
    if not _signing_key():
        return jsonify(
            {
                "error": "SECRET_KEY 또는 ADMIN_BOOTSTRAP_TOKEN 환경변수 필요",
                "hint": "Render Environment에서 설정 후 재배포",
            }
        ), 503

    nonce = secrets.token_urlsafe(18)
    exp = int(time.time()) + TTL_SECONDS
    issued_at = datetime.now(tz=timezone.utc).isoformat()
    payload = {"v": 1, "exp": exp, "nonce": nonce}
    token = _sign_payload(payload)
    _issued_nonces[nonce] = {"exp": exp, "issued_at": issued_at}
    _record_event(_issue_events)

    base_url = os.getenv("BASE_URL", "https://kohganepercentiii.com").rstrip("/")
    redeem_url = f"{base_url}/auth/diagnostic-token/redeem?token={token}"

    sys.stdout.write("\n" + _SEPARATOR + "\n")
    sys.stdout.write(f"🆘 DIAGNOSTIC TOKEN URL: {redeem_url}\n")
    sys.stdout.write(_SEPARATOR + "\n\n")
    sys.stdout.flush()

    logger.warning(_SEPARATOR)
    logger.warning("🆘 DIAGNOSTIC TOKEN 발급됨 (10분 유효, 1회용)")
    logger.warning("URL: %s", redeem_url)
    logger.warning("발급 IP: %s", request.remote_addr)
    logger.warning(_SEPARATOR)

    _notify_telegram_on_issue(ip=request.remote_addr, issued_at=issued_at)

    admin_emails_set = bool(os.getenv("ADMIN_EMAILS", "").strip())
    reveal_env = os.getenv("DIAGNOSTIC_REVEAL", "0") == "1"
    reveal_param = request.args.get("reveal_safe") == "1"

    can_reveal = reveal_env or (reveal_param and admin_emails_set)
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
        "issued_at": issued_at,
        "log_keyword": "DIAGNOSTIC TOKEN",
    }
    if can_reveal:
        payload["redeem_url"] = redeem_url
    return jsonify(payload)


@bp.get("/auth/diagnostic-token/redeem")
def redeem_token():
    token = request.args.get("token", "")
    if not token:
        return jsonify({"error": "토큰 누락"}), 400

    try:
        payload = _verify_token(token)
    except ValueError as exc:
        logger.info("Diagnostic token 검증 실패: %s", exc)
        return jsonify({"error": "유효하지 않은 토큰"}), 401
    except RuntimeError:
        return jsonify({"error": "토큰 검증 서버 설정 오류"}), 503

    nonce = str(payload.get("nonce", ""))
    if _is_used(nonce):
        return jsonify({"error": "이미 사용된 토큰"}), 401
    _mark_used(nonce, int(payload.get("exp", 0) or 0))
    _issued_nonces.pop(nonce, None)
    _record_event(_redeem_events)

    admin_emails = _admin_emails()
    if not admin_emails:
        return jsonify({"error": "ADMIN_EMAILS 환경변수 미설정"}), 503

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
        logger.warning("user_store 폴백 (직접 세션): %s", exc)
        session["user_id"] = "diagnostic-admin"
        session["user_email"] = primary_admin
        session["user_role"] = "admin"
        session["user_name"] = "Diagnostic Admin"

    logger.info("Diagnostic 토큰 redeem 성공: %s", primary_admin)
    return redirect("/admin/diagnostics")
