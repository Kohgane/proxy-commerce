"""src/feature_flags/gradual_rollout.py — 점진적 롤아웃."""
from __future__ import annotations

import hashlib


class GradualRollout:
    """비율 기반 + 해시 기반 일관성 점진적 롤아웃."""

    def is_included(self, flag_name: str, user_id: str, percentage: float) -> bool:
        """사용자가 롤아웃 대상에 포함되는지 확인 (해시 기반, 일관성 보장)."""
        if percentage >= 100.0:
            return True
        if percentage <= 0.0:
            return False
        # 해시 기반 버킷 (0~99)
        bucket = self._get_bucket(flag_name, user_id)
        return bucket < percentage

    def _get_bucket(self, flag_name: str, user_id: str) -> float:
        """해시로 버킷 번호 계산 (0.0 ~ 100.0)."""
        key = f"{flag_name}:{user_id}"
        digest = hashlib.sha256(key.encode()).hexdigest()
        bucket = int(digest[:8], 16) % 10000 / 100.0  # 0.0 ~ 99.99
        return bucket
