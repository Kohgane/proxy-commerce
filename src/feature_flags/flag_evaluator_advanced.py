"""src/feature_flags/flag_evaluator_advanced.py — 고도화 플래그 평가기."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .feature_flag import FeatureFlag, TargetingRule, Variant
from .gradual_rollout import GradualRollout
from .flag_override import FlagOverride
from .variant_manager import VariantManager


class FlagEvaluatorAdvanced:
    """컨텍스트 기반 고도화 플래그 평가 (타겟팅, 롤아웃, 변형, 오버라이드)."""

    def __init__(self) -> None:
        self._rollout = GradualRollout()
        self._override = FlagOverride()
        self._variant_mgr = VariantManager()

    def evaluate(self, flag: FeatureFlag, user_id: str = "",
                 context: Dict[str, Any] = None, environment: str = "") -> dict:
        """플래그 평가.

        Returns:
            {"enabled": bool, "variant": str|None, "reason": str}
        """
        context = context or {}

        # 1. 사용자 오버라이드 확인
        if user_id:
            override = self._override.get_user_override(flag.name, user_id)
            if override is not None:
                return self._result(override, None, "user_override")

        # 2. 환경 오버라이드 확인
        if environment:
            env_override = self._override.get_env_override(flag.name, environment)
            if env_override is not None:
                return self._result(env_override, None, "env_override")

        # 3. 플래그 비활성화
        if not flag.enabled:
            return self._result(False, None, "disabled")

        # 4. 타겟팅 규칙 평가 (모두 만족 시 활성화)
        if flag.rules:
            all_match = all(r.matches(context) for r in flag.rules)
            if not all_match:
                return self._result(False, None, "targeting_rule_failed")

        # 5. 점진적 롤아웃
        if user_id and flag.rollout_percentage < 100.0:
            if not self._rollout.is_included(flag.name, user_id, flag.rollout_percentage):
                return self._result(False, None, "rollout_excluded")

        # 6. 변형 할당
        variant = None
        if flag.variants:
            v = self._variant_mgr.assign_variant(flag.name, user_id, flag.variants)
            variant = v.name if v else None

        return self._result(True, variant, "enabled")

    def _result(self, enabled: bool, variant: Optional[str], reason: str) -> dict:
        return {"enabled": enabled, "variant": variant, "reason": reason}

    def get_override(self) -> FlagOverride:
        return self._override

    def get_variant_manager(self) -> VariantManager:
        return self._variant_mgr
