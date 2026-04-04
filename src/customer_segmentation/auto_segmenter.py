"""규칙 기반 자동 세그먼트 배정."""
from __future__ import annotations
from .segment_rules import SegmentRule

class AutoSegmenter:
    def __init__(self) -> None:
        self._rules: dict[str, list[SegmentRule]] = {}

    def add_rules(self, segment_id: str, rules: list[SegmentRule]) -> None:
        self._rules[segment_id] = rules

    def assign(self, customer: dict) -> list[str]:
        matched = []
        for seg_id, rules in self._rules.items():
            if all(r.matches(customer) for r in rules):
                matched.append(seg_id)
        return matched

    def assign_all(self, customers: list[dict]) -> dict[str, list[str]]:
        return {c.get("customer_id", str(i)): self.assign(c) for i, c in enumerate(customers)}
