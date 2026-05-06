"""src/messaging/channels/telegram_channel.py — 텔레그램 채널 (Phase 134)."""
from __future__ import annotations

import logging
import os

from src.messaging.channels.base import MessageChannel, _dry_run
from src.messaging.models import Recipient, SendResult

logger = logging.getLogger(__name__)


class TelegramNotifyChannel(MessageChannel):
    """텔레그램 알림 채널 (운영자/고객 단일 채팅)."""

    name = "telegram"

    @property
    def is_active(self) -> bool:
        return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))

    def send(self, recipient: Recipient, template_body: str, context: dict) -> SendResult:
        if _dry_run():
            return self._dry_run_send(recipient, template_body)

        chat_id = recipient.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not chat_id:
            return SendResult(sent=False, channel=self.name, error="no_chat_id")

        try:
            from src.notifications.telegram import send_telegram
            # 텔레그램은 수신자별 chat_id 직접 전송
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            if not bot_token:
                return SendResult(sent=False, channel=self.name, error="no_bot_token")

            import requests
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": template_body},
                timeout=5,
            )
            if resp.ok:
                msg_id = str(resp.json().get("result", {}).get("message_id", ""))
                return SendResult(sent=True, channel=self.name, provider_msg_id=msg_id)
            return SendResult(sent=False, channel=self.name, error=f"HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning("텔레그램 채널 오류: %s", exc)
            return SendResult(sent=False, channel=self.name, error=str(exc))

    def health_check(self) -> dict:
        status = "ok" if self.is_active else "missing_key"
        return {"name": self.name, "status": status, "detail": "TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID"}
