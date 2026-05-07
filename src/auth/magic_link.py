"""Magic Link 로그인 Blueprint."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .views import _resolve_user_role, _safe_next_url, establish_session

logger = logging.getLogger(__name__)

magic_link_bp = Blueprint("magic_link", __name__, template_folder="templates")

_LOCK = threading.Lock()
TOKEN_TTL_MINUTES = 15


def _tokens_file() -> Path:
    path = Path(os.getenv("MAGIC_LINK_TOKENS_PATH", "data/magic_link_tokens.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_records() -> list[dict]:
    path = _tokens_file()
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("Magic Link 토큰 레코드 파싱 실패")
    return records


def _write_records(records: list[dict]) -> None:
    path = _tokens_file()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    tmp_path.replace(path)


def _build_magic_link(raw_token: str, email: str, next_url: str) -> str:
    base_url = os.getenv("BASE_URL") or os.getenv("APP_BASE_URL") or "https://kohganepercentiii.com"
    query = {"token": raw_token, "email": email}
    if next_url:
        query["next"] = next_url
    return f"{base_url.rstrip('/')}/auth/magic-link/verify?{urlencode(query)}"


def _trusted_redirect_target(raw_next_url: str, default: str = "/seller/dashboard") -> str:
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


@magic_link_bp.get("/auth/magic-link")
def magic_link_request():
    """Magic Link 발송 폼 페이지."""
    next_url = _safe_next_url(request.args.get("next", ""))
    return render_template("auth/magic_link_request.html", next_url=next_url)


@magic_link_bp.post("/auth/magic-link")
def magic_link_send():
    """이메일에 1회용 로그인 링크 발송."""
    email = (request.form.get("email") or "").strip().lower()
    next_url = _safe_next_url(request.form.get("next", ""))
    if not email or "@" not in email:
        flash("올바른 이메일을 입력하세요.", "danger")
        return redirect(url_for("magic_link.magic_link_request", next=next_url))

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = _now_utc()
    record = {
        "token_hash": token_hash,
        "email": email,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=TOKEN_TTL_MINUTES)).isoformat(),
        "used": False,
    }

    with _LOCK:
        records = _load_records()
        records.append(record)
        _write_records(records)

    link = _build_magic_link(raw_token=raw_token, email=email, next_url=next_url)

    try:
        from src.messaging.resend_adapter import send_email

        sent_ok = send_email(
            to=email,
            subject="[코가네 퍼센티] 로그인 링크",
            html=(
                "<h2>로그인 링크</h2>"
                "<p>아래 버튼을 클릭하면 로그인됩니다 (15분 유효, 1회용).</p>"
                f"<p><a href=\"{link}\" style=\"background:#5850c8;color:#fff;padding:12px 24px;"
                "border-radius:8px;text-decoration:none\">로그인하기</a></p>"
                f"<p>또는 링크 복사: {link}</p>"
                "<hr><p>본인이 요청하지 않았다면 이 메일을 무시하세요.</p>"
            ),
            text=f"로그인 링크 (15분 유효): {link}",
        )
        if sent_ok:
            flash("이메일을 확인하세요. 로그인 링크가 발송되었습니다.", "success")
        else:
            logger.warning("Magic Link 발송 실패: email=%s", email)
            flash("이메일 발송에 실패했습니다. 운영자 로그를 확인하세요.", "danger")
    except Exception as exc:
        logger.warning("Magic Link 발송 실패: %s", exc)
        flash("이메일 발송에 실패했습니다. 운영자 로그를 확인하세요.", "danger")

    return redirect(url_for("magic_link.magic_link_request", next=next_url))


@magic_link_bp.get("/auth/magic-link/verify")
def magic_link_verify():
    """링크 클릭 → 토큰 검증 → 세션 생성."""
    raw_token = request.args.get("token", "")
    email = (request.args.get("email") or "").strip().lower()
    next_url = _safe_next_url(request.args.get("next", ""))

    if not raw_token or not email:
        flash("잘못된 링크입니다.", "danger")
        return redirect(url_for("magic_link.magic_link_request", next=next_url))

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    with _LOCK:
        records = _load_records()
        record = None
        for candidate in records:
            if (
                candidate.get("token_hash") == token_hash
                and candidate.get("email") == email
                and not candidate.get("used")
            ):
                record = candidate
                break

        if record is None:
            flash("토큰을 찾을 수 없거나 이미 사용되었습니다.", "danger")
            return redirect(url_for("magic_link.magic_link_request", next=next_url))

        if _now_utc() > _parse_dt(record.get("expires_at", "")):
            flash("토큰이 만료되었습니다 (15분).", "danger")
            return redirect(url_for("magic_link.magic_link_request", next=next_url))

        record["used"] = True
        _write_records(records)

    try:
        from src.auth.user_store import set_role, upsert_by_email

        role = _resolve_user_role(email)
        user = upsert_by_email(
            email=email,
            provider="magic_link",
            provider_id=email,
            name=email.split("@")[0],
        )
        user.role = role
        set_role(user.user_id, role)
        establish_session(user, role=role)
        flash(f"환영합니다, {email}님! ({role})", "success")
        return redirect(_trusted_redirect_target(next_url, default="/seller/dashboard"))
    except Exception as exc:
        logger.warning("Magic Link 사용자 저장 실패: %s", exc)
        flash("로그인 처리 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("magic_link.magic_link_request", next=next_url))
