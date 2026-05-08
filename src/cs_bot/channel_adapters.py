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
            "phase": "137",
        }


@dataclass
class StubCSAdapter:
    channel_name: str

    def is_enabled(self) -> bool:
        return True

    def status(self) -> dict:
        return {
            "channel": self.channel_name,
            "enabled": True,
            "mode": "stub",
            "phase": "138",
        }


def list_channel_adapters() -> list[CSChannelAdapter]:
    return [
        TelegramCSAdapter(),
        StubCSAdapter("kakao"),
        StubCSAdapter("email"),
        StubCSAdapter("coupang_qa"),
        StubCSAdapter("naver_talk"),
        StubCSAdapter("11st_qa"),
    ]
