"""src/notifications/email_resend.py — Resend 이메일 발송 (Phase 133).

SendGrid 대체. POST https://api.resend.com/emails
- Authorization: Bearer {RESEND_API_KEY}
- 키 미설정 시 noop + 로그
- ADAPTER_DRY_RUN=1 시 외부 호출 차단
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_FROM = "noreply@kohganepercentiii.com"


def send_email(
    to: "str | list[str]",
    subject: str,
    html: str,
    text: Optional[str] = None,
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> dict:
    """Resend로 이메일 발송.

    Args:
        to: 수신자 이메일 (문자열 또는 목록)
        subject: 제목
        html: HTML 본문
        text: 텍스트 대체 본문 (선택)
        from_email: 발신자 이메일 (미설정 시 RESEND_FROM_EMAIL 또는 기본값)
        reply_to: 회신 이메일 (선택)

    Returns:
        {"sent": True, "id": "..."} 또는 {"sent": False, "reason": "..."}
    """
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        logger.warning("RESEND_API_KEY 미설정 — 이메일 발송 건너뜀 (to=%s)", to)
        return {"sent": False, "reason": "RESEND_API_KEY 미설정"}

    if os.getenv("ADAPTER_DRY_RUN") == "1":
        logger.info("ADAPTER_DRY_RUN=1 — Resend 이메일 차단 (to=%s, subject=%s)", to, subject)
        return {"sent": False, "_dry_run": True, "to": to, "subject": subject}

    payload: dict = {
        "from": from_email or os.getenv("RESEND_FROM_EMAIL") or DEFAULT_FROM,
        "to": [to] if isinstance(to, str) else list(to),
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        r = requests.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        r.raise_for_status()
        return {"sent": True, "id": r.json().get("id")}
    except requests.HTTPError as exc:
        logger.warning("Resend 이메일 발송 실패 (HTTP %s): %s", exc.response.status_code, exc)
        return {"sent": False, "reason": f"HTTP {exc.response.status_code}"}
    except Exception as exc:
        logger.warning("Resend 이메일 발송 오류: %s", exc)
        return {"sent": False, "reason": "이메일 발송 중 오류가 발생했습니다."}


def health_check() -> dict:
    """API 키 유효성 light ping (도메인 정보 GET).

    Returns:
        {"status": "ok", "domains": N} 또는 {"status": "missing"|"fail", ...}
    """
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return {"status": "missing", "hint": "RESEND_API_KEY 환경변수 등록 필요"}
    try:
        r = requests.get(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5,
        )
        if r.status_code == 200:
            return {"status": "ok", "domains": len(r.json().get("data", []))}
        return {"status": "fail", "code": r.status_code}
    except Exception as exc:
        return {"status": "fail", "error": "Resend 헬스 체크 오류"}
