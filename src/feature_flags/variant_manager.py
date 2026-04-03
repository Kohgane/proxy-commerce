"""src/feature_flags/variant_manager.py — A/B 변형 관리."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from .feature_flag import Variant


class VariantManager:
    """A/B 변형 관리 (가중치 기반 할당, 사용자 고정)."""

    def __init__(self) -> None:
        self._assignments: Dict[str, Dict[str, str]] = {}  # flag_name -> {user_id: variant_name}

    def assign_variant(self, flag_name: str, user_id: str,
                       variants: List[Variant]) -> Optional[Variant]:
        """사용자에게 변형 할당 (일관성 보장)."""
        if not variants:
            return None
        # 이미 할당된 경우 동일 변형 반환
        user_assignments = self._assignments.setdefault(flag_name, {})
        if user_id in user_assignments:
            variant_name = user_assignments[user_id]
            for v in variants:
                if v.name == variant_name:
                    return v
        # 해시 기반 가중치 할당
        total_weight = sum(v.weight for v in variants)
        if total_weight <= 0:
            return variants[0]
        key = f"{flag_name}:{user_id}:variant"
        bucket = int(hashlib.md5(key.encode()).hexdigest()[:8], 16) / (2**32)
        cumulative = 0.0
        for variant in variants:
            cumulative += variant.weight / total_weight
            if bucket < cumulative:
                user_assignments[user_id] = variant.name
                return variant
        user_assignments[user_id] = variants[-1].name
        return variants[-1]

    def get_assignment(self, flag_name: str, user_id: str) -> Optional[str]:
        return self._assignments.get(flag_name, {}).get(user_id)

    def clear_assignment(self, flag_name: str, user_id: str) -> None:
        self._assignments.get(flag_name, {}).pop(user_id, None)
