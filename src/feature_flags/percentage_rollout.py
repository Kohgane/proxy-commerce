"""src/feature_flags/percentage_rollout.py — 비율 기반 롤아웃."""
from __future__ import annotations

import hashlib
from typing import Optional

from .rollout_strategy import RolloutStrategy


class PercentageRollout(RolloutStrategy):
    """user_id 해시 기반 결정론적 비율 롤아웃."""

    def __init__(self, percentage: float) -> None:
        if not 0 <= percentage <= 100:
            raise ValueError("percentage는 0~100 사이여야 합니다.")
        self.percentage = percentage

    def should_enable(self, user_id: Optional[str] = None, context: Optional[dict] = None) -> bool:
        if user_id is None:
            return False
        digest = hashlib.md5(user_id.encode()).hexdigest()
        bucket = int(digest[:8], 16) % 100
        return bucket < self.percentage
