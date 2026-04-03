"""src/realtime/realtime_hub.py — SSE 기반 실시간 이벤트 허브."""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field


@dataclass
class _Event:
    channel: str
    event_type: str
    data: dict
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )


class RealtimeHub:
    """SSE 기반 실시간 이벤트 허브."""

    def __init__(self) -> None:
        self._events: list[_Event] = []
        self._connected_clients: int = 0

    def publish(self, channel: str, event_type: str, data: dict) -> dict:
        """채널에 이벤트를 발행한다."""
        event = _Event(channel=channel, event_type=event_type, data=data)
        self._events.append(event)
        return {
            "event_id": event.event_id,
            "channel": channel,
            "event_type": event_type,
        }

    def get_recent_events(self, channel: str, limit: int = 20) -> list:
        """채널의 최근 이벤트를 반환한다."""
        filtered = [e for e in self._events if e.channel == channel]
        return [
            {
                "event_id": e.event_id,
                "channel": e.channel,
                "event_type": e.event_type,
                "data": e.data,
                "created_at": e.created_at.isoformat(),
            }
            for e in filtered[-limit:]
        ]

    def get_stats(self) -> dict:
        """허브 통계를 반환한다."""
        channels = {e.channel for e in self._events}
        return {
            "total_events": len(self._events),
            "active_channels": len(channels),
            "connected_clients": self._connected_clients,
        }
