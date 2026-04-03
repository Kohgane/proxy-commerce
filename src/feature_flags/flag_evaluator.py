"""src/feature_flags/flag_evaluator.py — 피쳐 플래그 평가기."""
from __future__ import annotations

from typing import Optional

from .feature_flag_manager import FeatureFlagManager
from .rollout_strategy import RolloutStrategy


class FlagEvaluator:
    """피쳐 플래그 활성화 여부 평가."""

    def __init__(self, manager: Optional[FeatureFlagManager] = None) -> None:
        self._manager = manager or FeatureFlagManager()
        self._strategies: dict = {}

    def set_strategy(self, flag_name: str, strategy: RolloutStrategy) -> None:
        self._strategies[flag_name] = strategy

    def evaluate(
        self,
        flag_name: str,
        user_id: Optional[str] = None,
        user_context: Optional[dict] = None,
    ) -> bool:
        flag = self._manager.get_flag(flag_name)
        if flag is None:
            return False
        if not flag.get("enabled"):
            return False
        strategy = self._strategies.get(flag_name)
        if strategy is not None:
            return strategy.should_enable(user_id=user_id, context=user_context)
        return True
