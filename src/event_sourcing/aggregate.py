"""src/event_sourcing/aggregate.py — 애그리게이트 기본 클래스."""
from __future__ import annotations

from typing import List

from .event import Event


class Aggregate:
    """이벤트 기반 애그리게이트."""

    def __init__(self, aggregate_id: str) -> None:
        self.aggregate_id = aggregate_id
        self._version = 0
        self._state: dict = {}

    def apply(self, event: Event) -> None:
        self._version = event.version
        self._state.update(event.data)

    def load_from_events(self, events: List[Event]) -> None:
        for event in events:
            self.apply(event)

    def get_version(self) -> int:
        return self._version

    def get_state(self) -> dict:
        return dict(self._state)
