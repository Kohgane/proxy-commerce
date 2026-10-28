"""src/notifications/email_resend.py — Resend 이메일 발송 (Phase 133).

ADAPTER_DRY_RUN=1 또는 RESEND_API_KEY 미설정 시 silently noop.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    html: str,
    from_email: Optional[str] = None,
    text: Optional[str] = None,
) -> bool:
    """Resend API로 이메일 발송.

    Args:
        to: 수신자 이메일 주소
        subject: 제목
        html: HTML 본문
        from_email: 발신자 (기본값: RESEND_FROM_EMAIL env)
        text: 텍스트 본문 (선택)

    Returns:
        발송 성공 시 True
    """
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        logger.info("ADAPTER_DRY_RUN=1 — 이메일 전송 차단: to=%s subject=%s", to, subject)
        return False

    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        logger.debug("RESEND_API_KEY 미설정 — 이메일 비활성")
        return False

    sender = from_email or os.getenv("RESEND_FROM_EMAIL", "noreply@kohganepercentiii.com")

    payload: dict = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    try:
        import requests
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        if resp.ok:
            msg_id = resp.json().get("id", "")
            logger.info("이메일 발송 성공: to=%s id=%s", to, msg_id)
            return True
        logger.warning("이메일 발송 실패 HTTP %s: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.warning("이메일 발송 오류: %s", exc)
        return False


def send_admin_email(subject: str, html: str) -> bool:
    """운영자(ADMIN_EMAILS)에게 이메일 발송.

    ADMIN_EMAILS: 쉼표로 구분된 이메일 목록
    """
    admin_emails_raw = os.getenv("ADMIN_EMAILS", "")
    if not admin_emails_raw:
        logger.debug("ADMIN_EMAILS 미설정 — 운영자 이메일 비활성")
        return False

    admin_emails = [e.strip() for e in admin_emails_raw.split(",") if e.strip()]
    ok = False
    for email in admin_emails:
        if send_email(email, subject, html):
            ok = True
    return ok


def health_check() -> dict:
    """/health/deep용 — 순찰 157(2026-10-28): 이 함수가 없어서 체크가 **항상 fail**이었다(import 오류를 삼킨 거짓 장애).
    정직 판정: 키 없음 → skip(비활성) · 키 있음 → Resend `GET /domains`로 실제 인증 1회(타임아웃 5s). 값은 로그·응답에 안 적는다."""
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        return {"status": "skip", "detail": "dry-run — 발송 비활성"}
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return {"status": "skip", "detail": "RESEND_API_KEY 미설정 — 이메일 알림 비활성"}
    try:
        import requests
        r = requests.get("https://api.resend.com/domains", headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
    except Exception as exc:                                     # noqa: BLE001
        return {"status": "fail", "detail": f"Resend 연결 실패 — {type(exc).__name__}"}
    if r.status_code == 200:
        try:
            n = len((r.json() or {}).get("data") or [])
        except Exception:                                        # noqa: BLE001
            n = -1
        return {"status": "ok", "detail": f"Resend 인증 OK · 도메인 {n}개" if n >= 0 else "Resend 인증 OK"}
    if r.status_code in (401, 403):
        return {"status": "fail", "detail": f"Resend 인증 실패 HTTP {r.status_code} — RESEND_API_KEY 확인"}
    return {"status": "warn", "detail": f"Resend 응답 HTTP {r.status_code}"}
