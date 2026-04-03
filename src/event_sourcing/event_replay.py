"""src/event_sourcing/event_replay.py — 이벤트 리플레이."""
from __future__ import annotations

from typing import List, Optional

from .event import Event


class EventReplay:
    """특정 타임스탬프 또는 버전까지 이벤트 리플레이."""

    def replay_until_version(self, events: List[Event], until_version: int) -> List[Event]:
        return [e for e in events if e.version <= until_version]

    def replay_until_timestamp(self, events: List[Event], until_timestamp: str) -> List[Event]:
        return [e for e in events if e.timestamp <= until_timestamp]

    def replay(self, events: List[Event], until_version: Optional[int] = None,
               until_timestamp: Optional[str] = None) -> List[Event]:
        result = events
        if until_version is not None:
            result = self.replay_until_version(result, until_version)
        if until_timestamp is not None:
            result = self.replay_until_timestamp(result, until_timestamp)
        return result
