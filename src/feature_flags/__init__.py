"""src/feature_flags/ — Phase 59/78: 피쳐 플래그."""
from __future__ import annotations

from .feature_flag_manager import FeatureFlagManager
from .flag_evaluator import FlagEvaluator
from .rollout_strategy import RolloutStrategy
from .percentage_rollout import PercentageRollout
from .user_target_rollout import UserTargetRollout
from .schedule_rollout import ScheduleRollout
from .flag_audit_log import FlagAuditLog
# Phase 78: 고도화
from .feature_flag import FeatureFlag, TargetingRule, Variant
from .gradual_rollout import GradualRollout
from .variant_manager import VariantManager
from .flag_history import FlagHistory, FlagHistoryEntry
from .flag_override import FlagOverride
from .flag_evaluator_advanced import FlagEvaluatorAdvanced

__all__ = [
    "FeatureFlagManager", "FlagEvaluator", "RolloutStrategy",
    "PercentageRollout", "UserTargetRollout", "ScheduleRollout",
    "FlagAuditLog",
    # Phase 78
    "FeatureFlag", "TargetingRule", "Variant",
    "GradualRollout", "VariantManager",
    "FlagHistory", "FlagHistoryEntry",
    "FlagOverride", "FlagEvaluatorAdvanced",
]
