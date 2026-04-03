"""src/event_sourcing/event_handler.py — 이벤트 핸들러 ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod

from .event import Event


class EventHandler(ABC):
    """이벤트 핸들러 기본 클래스."""

    @abstractmethod
    def handle(self, event: Event) -> None:
        """이벤트 처리."""
