"""src/feature_flags/schedule_rollout.py — 일정 기반 롤아웃."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .rollout_strategy import RolloutStrategy


class ScheduleRollout(RolloutStrategy):
    """지정된 시각 이후 자동 활성화."""

    def __init__(self, enable_at: datetime) -> None:
        self.enable_at = enable_at

    def should_enable(self, user_id: Optional[str] = None, context: Optional[dict] = None) -> bool:
        now = datetime.now(tz=timezone.utc)
        # Make enable_at timezone-aware if needed
        ea = self.enable_at
        if ea.tzinfo is None:
            ea = ea.replace(tzinfo=timezone.utc)
        return now >= ea
