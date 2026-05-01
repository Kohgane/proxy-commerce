"""monitoring/notifier.py — Alert notifier (Telegram + Slack).

Covers issue #92: send alert messages when a :class:`ChangeEvent` is detected.

Configure via environment variables:

Telegram:
    TELEGRAM_BOT_TOKEN   — Bot token (required for Telegram)
    TELEGRAM_CHAT_ID     — Chat / channel ID (required for Telegram)

Slack:
    SLACK_WEBHOOK_URL    — Incoming-webhook URL (required for Slack)

Example:
    from monitoring.notifier import Notifier, ChangeEvent
    notifier = Notifier.from_env()
    notifier.notify(event)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Optional, Sequence, Union
from urllib.error import URLError

from monitoring.watcher import ChangeEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Low-level HTTP helpers (no external deps)
# ---------------------------------------------------------------------------


def _post_json(url: str, payload: dict, timeout: int = 10) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"HTTP POST to {url} failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------


class TelegramBackend:
    """Send alerts via the Telegram Bot API ``sendMessage`` method."""

    API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, token: str, chat_id: str) -> None:
        if not token or not chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must not be empty")
        self.token = token
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        url = self.API_URL.format(token=self.token)
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        try:
            _post_json(url, payload)
            logger.info("[notifier:telegram] Message sent to chat %s", self.chat_id)
        except RuntimeError as exc:
            logger.error("[notifier:telegram] Failed to send message: %s", exc)
            raise


class SlackBackend:
    """Send alerts via a Slack Incoming Webhook URL."""

    def __init__(self, webhook_url: str) -> None:
        if not webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL must not be empty")
        self.webhook_url = webhook_url

    def send(self, text: str) -> None:
        payload = {"text": text}
        try:
            _post_json(self.webhook_url, payload)
            logger.info("[notifier:slack] Message sent to webhook")
        except RuntimeError as exc:
            logger.error("[notifier:slack] Failed to send message: %s", exc)
            raise


# ---------------------------------------------------------------------------
# High-level Notifier
# ---------------------------------------------------------------------------


def _format_event(event: ChangeEvent) -> str:
    field_labels = {
        "cost_price": "💰 Cost price",
        "sell_price": "🏷️ Sell price",
        "stock_status": "📦 Stock status",
    }
    label = field_labels.get(event.field, event.field)
    return (
        f"⚠️ <b>Product alert</b>\n"
        f"Source: {event.source}\n"
        f"Product: {event.title or event.source_product_id}\n"
        f"{label}: {event.old_value!r} → {event.new_value!r}"
    )


class Notifier:
    """Sends change-event alerts to one or more backends.

    Parameters
    ----------
    backends:
        One or more backend objects (TelegramBackend, SlackBackend, or any
        object with a ``send(text: str)`` method).
    """

    def __init__(self, backends: Sequence) -> None:
        self._backends = list(backends)
        if not self._backends:
            logger.warning("[notifier] No backends configured — alerts will be logged only")

    @classmethod
    def from_env(cls) -> "Notifier":
        """Build a Notifier from environment variables.

        Activates Telegram if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID are set.
        Activates Slack if SLACK_WEBHOOK_URL is set.
        Falls back to a no-op (log-only) notifier if neither is configured.
        """
        backends = []

        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat = os.getenv("TELEGRAM_CHAT_ID")
        if telegram_token and telegram_chat:
            backends.append(TelegramBackend(telegram_token, telegram_chat))
            logger.info("[notifier] Telegram backend enabled (chat=%s)", telegram_chat)

        slack_url = os.getenv("SLACK_WEBHOOK_URL")
        if slack_url:
            backends.append(SlackBackend(slack_url))
            logger.info("[notifier] Slack backend enabled")

        if not backends:
            logger.warning(
                "[notifier] No alert backends configured. "
                "Set TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID or SLACK_WEBHOOK_URL."
            )

        return cls(backends)

    def notify(self, event: ChangeEvent) -> None:
        """Format *event* and dispatch to all backends."""
        text = _format_event(event)
        logger.info("[notifier] Dispatching alert: %s", str(event))
        for backend in self._backends:
            try:
                backend.send(text)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("[notifier] Backend %s failed: %s", type(backend).__name__, exc)

    def notify_batch(self, events: Sequence[ChangeEvent]) -> None:
        """Notify all events in *events*."""
        for event in events:
            self.notify(event)
