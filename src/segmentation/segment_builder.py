"""src/segmentation/segment_builder.py — 규칙 기반 세그먼트 빌더."""
from __future__ import annotations

from typing import Any, Dict, List

from .segment_rule import SegmentRule


class SegmentBuilder:
    """AND/OR 조합으로 세그먼트 조건 구성."""

    def __init__(self, logic: str = "AND") -> None:
        """
        logic: 'AND' (모든 규칙 만족) 또는 'OR' (하나라도 만족)
        """
        if logic not in ("AND", "OR"):
            raise ValueError("logic은 'AND' 또는 'OR'이어야 합니다")
        self.logic = logic
        self._rules: List[SegmentRule] = []

    def add_rule(self, field: str, operator: str, value: Any) -> "SegmentBuilder":
        """규칙 추가 후 자신을 반환 (체이닝 지원)."""
        self._rules.append(SegmentRule(field=field, operator=operator, value=value))
        return self

    def build(self) -> List[SegmentRule]:
        return list(self._rules)

    def matches(self, customer: Dict[str, Any]) -> bool:
        """고객이 빌더의 규칙을 만족하는지 확인."""
        if not self._rules:
            return True
        if self.logic == "AND":
            return all(r.evaluate(customer) for r in self._rules)
        return any(r.evaluate(customer) for r in self._rules)
