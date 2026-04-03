"""src/event_sourcing/event_store.py — 이벤트 저장소 (append-only)."""
from __future__ import annotations

from typing import List

from .event import Event


class EventStore:
    """이벤트 추가/조회 (append-only)."""

    def __init__(self) -> None:
        self._events: List[Event] = []

    def append(self, event: Event) -> None:
        self._events.append(event)

    def get_events(self, aggregate_id: str) -> List[Event]:
        return [e for e in self._events if e.aggregate_id == aggregate_id]

    def get_all(self) -> List[Event]:
        return list(self._events)

    def get_since(self, timestamp: str) -> List[Event]:
        return [e for e in self._events if e.timestamp >= timestamp]
