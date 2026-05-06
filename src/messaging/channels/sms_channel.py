"""src/messaging/channels/sms_channel.py — SMS 채널 (Twilio / Aligo) (Phase 134).

글로벌: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM
한국: ALIGO_API_KEY, ALIGO_USER_ID, ALIGO_SENDER
"""
from __future__ import annotations

import logging
import os

from src.messaging.channels.base import MessageChannel, _dry_run
from src.messaging.models import Recipient, SendResult

logger = logging.getLogger(__name__)


class SMSChannel(MessageChannel):
    """SMS 채널 — Twilio(글로벌) 우선, Aligo(한국) 폴백."""

    name = "sms"

    @property
    def is_active(self) -> bool:
        twilio_ok = bool(
            os.getenv("TWILIO_ACCOUNT_SID")
            and os.getenv("TWILIO_AUTH_TOKEN")
            and os.getenv("TWILIO_FROM")
        )
        aligo_ok = bool(
            os.getenv("ALIGO_API_KEY")
            and os.getenv("ALIGO_USER_ID")
            and os.getenv("ALIGO_SENDER")
        )
        return twilio_ok or aligo_ok

    def send(self, recipient: Recipient, template_body: str, context: dict) -> SendResult:
        if _dry_run():
            return self._dry_run_send(recipient, template_body)

        if not self.is_active:
            return SendResult(sent=False, channel=self.name, error="not_configured")

        phone = recipient.phone_e164
        if not phone:
            return SendResult(sent=False, channel=self.name, error="no_phone")

        # 한국 번호이고 Aligo 활성이면 Aligo 우선
        if phone.startswith("+82") and os.getenv("ALIGO_API_KEY"):
            return self._send_aligo(phone, template_body, recipient.name)

        # 그 외 Twilio
        if os.getenv("TWILIO_ACCOUNT_SID"):
            return self._send_twilio(phone, template_body)

        return SendResult(sent=False, channel=self.name, error="no_provider")

    def _send_twilio(self, phone: str, body: str) -> SendResult:
        try:
            import requests
            account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
            auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
            from_num = os.getenv("TWILIO_FROM", "")
            resp = requests.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                data={"From": from_num, "To": phone, "Body": body},
                auth=(account_sid, auth_token),
                timeout=10,
            )
            if resp.ok:
                msg_id = resp.json().get("sid", "")
                return SendResult(sent=True, channel=self.name, provider_msg_id=msg_id)
            return SendResult(sent=False, channel=self.name, error=f"HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning("Twilio SMS 오류: %s", exc)
            return SendResult(sent=False, channel=self.name, error=str(exc))

    def _send_aligo(self, phone: str, body: str, name: str = "") -> SendResult:
        try:
            import requests
            # Aligo: +82XXXXXXXXX → 010XXXXXXXX
            local_phone = "0" + phone[3:] if phone.startswith("+82") else phone
            payload = {
                "key": os.getenv("ALIGO_API_KEY", ""),
                "user_id": os.getenv("ALIGO_USER_ID", ""),
                "sender": os.getenv("ALIGO_SENDER", ""),
                "receiver": local_phone,
                "msg": body[:90],  # SMS 90바이트
                "rdate": "",
                "rtime": "",
            }
            resp = requests.post(
                "https://apis.aligo.in/send/",
                data=payload,
                timeout=10,
            )
            data = resp.json()
            if str(data.get("result_code", "")) == "1":
                return SendResult(sent=True, channel=self.name)
            return SendResult(
                sent=False,
                channel=self.name,
                error=str(data.get("message", "aligo_error")),
            )
        except Exception as exc:
            logger.warning("Aligo SMS 오류: %s", exc)
            return SendResult(sent=False, channel=self.name, error=str(exc))

    def health_check(self) -> dict:
        status = "ok" if self.is_active else "missing_key"
        return {
            "name": self.name,
            "status": status,
            "detail": "TWILIO_* 또는 ALIGO_*",
        }
