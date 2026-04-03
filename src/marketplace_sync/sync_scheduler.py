"""src/marketplace_sync/sync_scheduler.py — 동기화 스케줄러."""
from __future__ import annotations

import datetime


class SyncScheduler:
    """동기화 스케줄러."""

    def __init__(self) -> None:
        self._schedules: dict[str, dict] = {}

    def schedule(self, marketplace: str, interval_minutes: int = 60) -> dict:
        """동기화 스케줄을 등록한다."""
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        entry = {
            "marketplace": marketplace,
            "interval_minutes": interval_minutes,
            "next_sync": (now + datetime.timedelta(minutes=interval_minutes)).isoformat(),
            "last_sync": None,
            "created_at": now.isoformat(),
        }
        self._schedules[marketplace] = entry
        return entry

    def get_schedule(self, marketplace: str) -> dict:
        """스케줄을 반환한다."""
        return self._schedules.get(marketplace, {})

    def list_schedules(self) -> list:
        """모든 스케줄 목록을 반환한다."""
        return list(self._schedules.values())

    def should_sync(self, marketplace: str) -> bool:
        """동기화가 필요한지 확인한다."""
        schedule = self._schedules.get(marketplace)
        if not schedule:
            return False
        next_sync = schedule.get("next_sync")
        if not next_sync:
            return True
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        next_dt = datetime.datetime.fromisoformat(next_sync)
        return now >= next_dt
