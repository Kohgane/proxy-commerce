"""src/realtime/event_stream.py — 이벤트 스트림."""
from __future__ import annotations

import datetime


class EventStream:
    """채널 기반 이벤트 스트림."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[str]] = {}
        self._history: list[dict] = []

    def subscribe(self, channel: str, client_id: str) -> None:
        """채널에 클라이언트를 구독한다."""
        self._subscribers.setdefault(channel, set()).add(client_id)

    def unsubscribe(self, channel: str, client_id: str) -> None:
        """채널에서 클라이언트를 구독 해제한다."""
        if channel in self._subscribers:
            self._subscribers[channel].discard(client_id)

    def publish(self, channel: str, data: dict) -> int:
        """채널에 데이터를 발행하고 구독자 수를 반환한다."""
        record = {
            "channel": channel,
            "data": data,
            "published_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
        self._history.append(record)
        return len(self._subscribers.get(channel, set()))

    def get_subscribers(self, channel: str) -> list:
        """채널의 구독자 목록을 반환한다."""
        return list(self._subscribers.get(channel, set()))
