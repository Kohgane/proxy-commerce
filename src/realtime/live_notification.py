"""src/realtime/live_notification.py — 실시간 알림."""
from __future__ import annotations

import datetime
import uuid


class LiveNotification:
    """실시간 알림 관리."""

    def __init__(self) -> None:
        self._notifications: list[dict] = []

    def push(self, event_type: str, payload: dict) -> dict:
        """알림을 발행한다."""
        notification = {
            "notification_id": str(uuid.uuid4()),
            "event_type": event_type,
            "payload": payload,
            "created_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
        self._notifications.append(notification)
        return notification

    def get_recent(self, limit: int = 10) -> list:
        """최근 알림 목록을 반환한다."""
        return self._notifications[-limit:]

    def clear(self) -> int:
        """알림을 모두 지우고 지운 수를 반환한다."""
        count = len(self._notifications)
        self._notifications.clear()
        return count
