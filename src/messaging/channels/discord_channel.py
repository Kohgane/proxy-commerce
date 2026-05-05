"""src/messaging/channels/discord_channel.py — Discord Webhook 채널 (Phase 134).

DISCORD_WEBHOOK_URL 환경변수 필요.
"""
from __future__ import annotations

import logging
import os

from src.messaging.channels.base import MessageChannel, _dry_run
from src.messaging.models import Recipient, SendResult

logger = logging.getLogger(__name__)


class DiscordChannel(MessageChannel):
    """Discord Webhook 채널 (운영자 알림 보조)."""

    name = "discord"

    @property
    def is_active(self) -> bool:
        return bool(os.getenv("DISCORD_WEBHOOK_URL"))

    def send(self, recipient: Recipient, template_body: str, context: dict) -> SendResult:
        if _dry_run():
            return self._dry_run_send(recipient, template_body)

        if not self.is_active:
            return SendResult(sent=False, channel=self.name, error="not_configured")

        try:
            import requests
            webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
            payload = {"content": template_body[:2000]}
            username = context.get("username", "코가네 알림")
            payload["username"] = username
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.ok or resp.status_code == 204:
                return SendResult(sent=True, channel=self.name)
            return SendResult(sent=False, channel=self.name, error=f"HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning("Discord 채널 오류: %s", exc)
            return SendResult(sent=False, channel=self.name, error=str(exc))

    def health_check(self) -> dict:
        status = "ok" if self.is_active else "missing_key"
        return {"name": self.name, "status": status, "detail": "DISCORD_WEBHOOK_URL"}
