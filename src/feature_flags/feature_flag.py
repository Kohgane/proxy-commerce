"""src/feature_flags/feature_flag.py — 피처 플래그 데이터클래스."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class TargetingRule:
    """타겟팅 규칙."""
    attribute: str      # 사용자 속성 키
    operator: str       # eq, neq, in, not_in, gt, lt
    value: Any
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def matches(self, context: Dict[str, Any]) -> bool:
        actual = context.get(self.attribute)
        if actual is None:
            return False
        op = self.operator
        v = self.value
        if op == "eq":
            return actual == v
        if op == "neq":
            return actual != v
        if op == "in":
            return actual in (v if isinstance(v, list) else [v])
        if op == "not_in":
            return actual not in (v if isinstance(v, list) else [v])
        try:
            if op == "gt":
                return float(actual) > float(v)
            if op == "lt":
                return float(actual) < float(v)
        except (TypeError, ValueError):
            pass
        return False

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "attribute": self.attribute,
            "operator": self.operator,
            "value": self.value,
        }


@dataclass
class Variant:
    """A/B 테스트 변형."""
    name: str
    value: Any
    weight: float = 1.0     # 상대 가중치

    def to_dict(self) -> dict:
        return {"name": self.name, "value": self.value, "weight": self.weight}


@dataclass
class FeatureFlag:
    """피처 플래그 정의."""
    name: str
    enabled: bool = False
    description: str = ""
    rules: List[TargetingRule] = field(default_factory=list)
    rollout_percentage: float = 100.0
    variants: List[Variant] = field(default_factory=list)
    flag_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "flag_id": self.flag_id,
            "name": self.name,
            "enabled": self.enabled,
            "description": self.description,
            "rules": [r.to_dict() for r in self.rules],
            "rollout_percentage": self.rollout_percentage,
            "variants": [v.to_dict() for v in self.variants],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
