"""src/integrations/slack_connector.py — Slack 연동 모의 구현."""
from __future__ import annotations

from typing import List

from .integration_connector import IntegrationConnector


class SlackConnector(IntegrationConnector):
    """Slack 웹훅 연동 모의 구현 (실제 API 호출 없음)."""

    name = "slack"

    def __init__(self, webhook_url: str = "https://hooks.slack.com/mock") -> None:
        self.webhook_url = webhook_url
        self._connected = False
        self._messages: List[dict] = []

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def health_check(self) -> dict:
        return {"name": self.name, "status": "ok" if self._connected else "disconnected"}

    def send_message(self, channel: str, text: str) -> dict:
        msg = {"channel": channel, "text": text}
        self._messages.append(msg)
        return {"ok": True, "message": msg}

    def sync(self) -> dict:
        result = self.send_message("#status", "✅ Proxy Commerce 시스템 정상")
        return {"synced": True, "message_sent": result}

    def get_messages(self) -> List[dict]:
        return list(self._messages)
