"""src/segmentation/segment_rule.py — 세그먼트 조건 정의."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SegmentRule:
    """세그먼트 규칙 조건.

    field: 조건 필드 (total_purchase_amount, purchase_count, days_since_last_purchase, region, channel)
    operator: 비교 연산자 (gt, gte, lt, lte, eq, neq, in, not_in)
    value: 비교 값
    """

    field: str
    operator: str
    value: Any
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # 지원 필드
    SUPPORTED_FIELDS = {
        "total_purchase_amount",
        "purchase_count",
        "days_since_last_purchase",
        "region",
        "channel",
    }

    # 지원 연산자
    SUPPORTED_OPERATORS = {"gt", "gte", "lt", "lte", "eq", "neq", "in", "not_in"}

    def evaluate(self, customer: Dict[str, Any]) -> bool:
        """고객 데이터에 규칙 적용."""
        actual = customer.get(self.field)
        if actual is None:
            return False
        op = self.operator
        v = self.value
        try:
            if op == "gt":
                return float(actual) > float(v)
            if op == "gte":
                return float(actual) >= float(v)
            if op == "lt":
                return float(actual) < float(v)
            if op == "lte":
                return float(actual) <= float(v)
            if op == "eq":
                return actual == v
            if op == "neq":
                return actual != v
            if op == "in":
                return actual in (v if isinstance(v, list) else [v])
            if op == "not_in":
                return actual not in (v if isinstance(v, list) else [v])
        except (TypeError, ValueError):
            return False
        return False

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "field": self.field,
            "operator": self.operator,
            "value": self.value,
        }
