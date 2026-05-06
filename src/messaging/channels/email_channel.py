"""src/messaging/channels/email_channel.py — Resend 이메일 채널 (Phase 134)."""
from __future__ import annotations

import logging
import os

from src.messaging.channels.base import MessageChannel, _dry_run
from src.messaging.models import Recipient, SendResult

logger = logging.getLogger(__name__)


class ResendChannel(MessageChannel):
    """Resend 이메일 채널."""

    name = "email"

    @property
    def is_active(self) -> bool:
        return bool(os.getenv("RESEND_API_KEY"))

    def send(self, recipient: Recipient, template_body: str, context: dict) -> SendResult:
        if _dry_run():
            return self._dry_run_send(recipient, template_body)

        if not recipient.email:
            return SendResult(sent=False, channel=self.name, error="no_email")

        try:
            from src.notifications.email_resend import send_email
            subject = context.get("subject", "코가네 알림")
            html_body = template_body if "<" in template_body else f"<p>{template_body}</p>"
            ok = send_email(recipient.email, subject, html_body)
            return SendResult(sent=ok, channel=self.name)
        except Exception as exc:
            logger.warning("이메일 채널 발송 오류: %s", exc)
            return SendResult(sent=False, channel=self.name, error=str(exc))

    def health_check(self) -> dict:
        status = "ok" if self.is_active else "missing_key"
        return {"name": self.name, "status": status, "detail": "RESEND_API_KEY"}
