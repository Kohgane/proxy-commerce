"""src/messaging/channels/whatsapp_channel.py — WhatsApp Business Cloud API 채널 (Phase 134).

META_WHATSAPP_TOKEN, META_WHATSAPP_PHONE_ID 환경변수 필요.
"""
from __future__ import annotations

import logging
import os

from src.messaging.channels.base import MessageChannel, _dry_run
from src.messaging.models import Recipient, SendResult

logger = logging.getLogger(__name__)


class WhatsAppChannel(MessageChannel):
    """WhatsApp Business Cloud API 채널."""

    name = "whatsapp"

    @property
    def is_active(self) -> bool:
        return bool(
            os.getenv("META_WHATSAPP_TOKEN")
            and os.getenv("META_WHATSAPP_PHONE_ID")
        )

    def send(self, recipient: Recipient, template_body: str, context: dict) -> SendResult:
        if _dry_run():
            return self._dry_run_send(recipient, template_body)

        if not self.is_active:
            return SendResult(sent=False, channel=self.name, error="not_configured")

        phone = recipient.whatsapp_phone or recipient.phone_e164
        if not phone:
            return SendResult(sent=False, channel=self.name, error="no_phone")

        try:
            import requests
            token = os.getenv("META_WHATSAPP_TOKEN", "")
            phone_id = os.getenv("META_WHATSAPP_PHONE_ID", "")
            # E.164 형식 정규화
            to_phone = phone.lstrip("+").replace("-", "").replace(" ", "")

            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "text",
                "text": {"body": template_body},
            }
            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{phone_id}/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                msg_id = data.get("messages", [{}])[0].get("id", "")
                return SendResult(sent=True, channel=self.name, provider_msg_id=msg_id)
            return SendResult(sent=False, channel=self.name, error=f"HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning("WhatsApp 채널 오류: %s", exc)
            return SendResult(sent=False, channel=self.name, error=str(exc))

    def health_check(self) -> dict:
        status = "ok" if self.is_active else "missing_key"
        return {
            "name": self.name,
            "status": status,
            "detail": "META_WHATSAPP_TOKEN + META_WHATSAPP_PHONE_ID",
        }
