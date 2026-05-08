from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


class CSChannelAdapter(Protocol):
    channel_name: str

    def is_enabled(self) -> bool: ...

    def status(self) -> dict: ...


@dataclass
class TelegramCSAdapter:
    channel_name: str = "telegram"

    def is_enabled(self) -> bool:
        return bool(os.getenv("TELEGRAM_BOT_TOKEN"))

    def status(self) -> dict:
        return {
            "channel": self.channel_name,
            "enabled": self.is_enabled(),
            "mode": "webhook",
            "phase": "138",
        }


@dataclass
class _ChannelAdapterWrapper:
    """Wraps InboundChannelAdapter for status() compatibility."""
    _adapter: object

    @property
    def channel_name(self) -> str:
        return getattr(self._adapter, "name", "unknown")

    def is_enabled(self) -> bool:
        try:
            return bool(self._adapter.is_active())  # type: ignore
        except Exception:
            return False

    def status(self) -> dict:
        return {
            "channel": self.channel_name,
            "enabled": self.is_enabled(),
            "mode": "poll",
            "phase": "138",
        }


def list_channel_adapters() -> list:
    adapters = [TelegramCSAdapter()]
    try:
        from src.cs_bot.channels.email_imap import EmailImapAdapter
        from src.cs_bot.channels.coupang_qa import CoupangQAAdapter
        from src.cs_bot.channels.naver_talk import NaverTalkAdapter
        from src.cs_bot.channels.eleven_qa import ElevenQAAdapter
        for cls in [EmailImapAdapter, CoupangQAAdapter, NaverTalkAdapter, ElevenQAAdapter]:
            adapters.append(_ChannelAdapterWrapper(cls()))
    except Exception:
        pass
    return adapters

