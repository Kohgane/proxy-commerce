"""src/backup/backup_scheduler.py — 백업 스케줄러."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


VALID_FREQUENCIES = {"daily", "weekly", "monthly"}


class BackupScheduler:
    """백업 스케줄 관리."""

    def __init__(self) -> None:
        self._schedule: Dict[str, str] = {
            "frequency": "daily",
            "updated_at": _now_iso(),
        }

    def get_schedule(self) -> dict:
        return dict(self._schedule)

    def set_schedule(self, frequency: str) -> dict:
        if frequency not in VALID_FREQUENCIES:
            raise ValueError(f"유효하지 않은 주기: {frequency}. {VALID_FREQUENCIES}")
        self._schedule["frequency"] = frequency
        self._schedule["updated_at"] = _now_iso()
        return dict(self._schedule)
