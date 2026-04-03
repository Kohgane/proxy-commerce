"""src/feature_flags/user_target_rollout.py — 특정 사용자 대상 롤아웃."""
from __future__ import annotations

from typing import List, Optional

from .rollout_strategy import RolloutStrategy


class UserTargetRollout(RolloutStrategy):
    """지정된 user_id 목록에 대해서만 활성화."""

    def __init__(self, user_ids: List[str]) -> None:
        self.user_ids: List[str] = list(user_ids)

    def should_enable(self, user_id: Optional[str] = None, context: Optional[dict] = None) -> bool:
        if user_id is None:
            return False
        return user_id in self.user_ids
