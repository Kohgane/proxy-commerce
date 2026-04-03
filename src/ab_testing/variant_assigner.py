"""src/ab_testing/variant_assigner.py — 해시 기반 사용자 변형 할당."""
from __future__ import annotations

import hashlib
from typing import List


class VariantAssigner:
    """사용자를 변형(variant)에 일관되게 할당 (해시 기반)."""

    def assign(self, experiment_id: str, user_id: str, variants: List[str] = None) -> str:
        """실험 + 사용자 ID를 해시하여 변형 할당 (SHA-256 기반, 보안 목적 아님)."""
        if variants is None:
            variants = ["control", "treatment"]
        if not variants:
            raise ValueError("variants 목록이 비어 있습니다.")
        key = f"{experiment_id}:{user_id}"
        # NOTE: SHA-256 사용 (variant 할당용 — 보안/인증 목적 아님)
        digest = hashlib.sha256(key.encode()).hexdigest()
        index = int(digest, 16) % len(variants)
        return variants[index]

    def assign_weighted(self, experiment_id: str, user_id: str, weights: dict) -> str:
        """가중치 기반 변형 할당 (weights: {'control': 0.5, 'treatment': 0.5})."""
        if not weights:
            raise ValueError("weights는 비어 있을 수 없습니다.")
        key = f"{experiment_id}:{user_id}"
        # NOTE: SHA-256 사용 (variant 할당용 — 보안/인증 목적 아님)
        digest = hashlib.sha256(key.encode()).hexdigest()
        bucket = (int(digest, 16) % 10000) / 10000.0  # 0.0 ~ 0.9999

        cumulative = 0.0
        for variant, weight in weights.items():
            cumulative += weight
            if bucket < cumulative:
                return variant
        # fallback: 마지막 변형
        return list(weights.keys())[-1]
