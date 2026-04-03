"""src/event_sourcing/event_bus.py — 이벤트 버스 (pub-sub)."""
from __future__ import annotations

from typing import Callable, Dict, List

from .event import Event


class EventBus:
    """이벤트 발행/구독."""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._handlers.get(event.event_type, []):
            handler.handle(event) if hasattr(handler, "handle") else handler(event)
        # Wildcard subscribers
        for handler in self._handlers.get("*", []):
            handler.handle(event) if hasattr(handler, "handle") else handler(event)
