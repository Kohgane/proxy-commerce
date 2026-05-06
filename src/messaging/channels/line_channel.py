"""src/messaging/channels/line_channel.py — LINE Notify / LINE Messaging API 채널 (Phase 134).

LINE_NOTIFY_TOKEN: LINE Notify (간단, 채널 공지 알림)
LINE_CHANNEL_ACCESS_TOKEN + LINE_CHANNEL_SECRET: LINE Messaging API (개인 DM)
"""
from __future__ import annotations

import logging
import os

from src.messaging.channels.base import MessageChannel, _dry_run
from src.messaging.models import Recipient, SendResult

logger = logging.getLogger(__name__)


class LineNotifyChannel(MessageChannel):
    """LINE Notify 채널 (그룹/채널 공지)."""

    name = "line_notify"

    @property
    def is_active(self) -> bool:
        return bool(os.getenv("LINE_NOTIFY_TOKEN"))

    def send(self, recipient: Recipient, template_body: str, context: dict) -> SendResult:
        if _dry_run():
            return self._dry_run_send(recipient, template_body)

        if not self.is_active:
            return SendResult(sent=False, channel=self.name, error="not_configured")

        try:
            import requests
            token = os.getenv("LINE_NOTIFY_TOKEN", "")
            resp = requests.post(
                "https://notify-api.line.me/api/notify",
                headers={"Authorization": f"Bearer {token}"},
                data={"message": f"\n{template_body}"},
                timeout=10,
            )
            if resp.ok:
                return SendResult(sent=True, channel=self.name)
            return SendResult(sent=False, channel=self.name, error=f"HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning("LINE Notify 오류: %s", exc)
            return SendResult(sent=False, channel=self.name, error=str(exc))

    def health_check(self) -> dict:
        status = "ok" if self.is_active else "missing_key"
        return {"name": self.name, "status": status, "detail": "LINE_NOTIFY_TOKEN"}


class LineMessagingChannel(MessageChannel):
    """LINE Messaging API 채널 (1:1 DM)."""

    name = "line"

    @property
    def is_active(self) -> bool:
        return bool(
            os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
            and os.getenv("LINE_CHANNEL_SECRET")
        )

    def send(self, recipient: Recipient, template_body: str, context: dict) -> SendResult:
        if _dry_run():
            return self._dry_run_send(recipient, template_body)

        if not self.is_active:
            return SendResult(sent=False, channel=self.name, error="not_configured")

        if not recipient.line_user_id:
            return SendResult(sent=False, channel=self.name, error="no_line_user_id")

        try:
            import requests
            token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
            payload = {
                "to": recipient.line_user_id,
                "messages": [{"type": "text", "text": template_body}],
            }
            resp = requests.post(
                "https://api.line.me/v2/bot/message/push",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            if resp.ok:
                return SendResult(sent=True, channel=self.name)
            return SendResult(sent=False, channel=self.name, error=f"HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning("LINE Messaging 오류: %s", exc)
            return SendResult(sent=False, channel=self.name, error=str(exc))

    def health_check(self) -> dict:
        status = "ok" if self.is_active else "missing_key"
        return {
            "name": self.name,
            "status": status,
            "detail": "LINE_CHANNEL_ACCESS_TOKEN + LINE_CHANNEL_SECRET",
        }
