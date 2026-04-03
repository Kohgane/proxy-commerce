"""src/feature_flags/rollout_strategy.py — 롤아웃 전략 ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class RolloutStrategy(ABC):
    """피쳐 플래그 롤아웃 전략 추상 기반 클래스."""

    @abstractmethod
    def should_enable(self, user_id: Optional[str] = None, context: Optional[dict] = None) -> bool:
        """사용자에게 기능 활성화 여부 반환."""
