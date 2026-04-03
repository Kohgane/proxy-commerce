"""src/rules_engine/rule_set.py — 규칙 집합."""
from __future__ import annotations

from .rule import Rule


class RuleSet:
    """규칙 집합."""

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._rules: list[Rule] = []

    def add_rule(self, rule: Rule) -> None:
        """규칙을 추가한다."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, rule_id: str) -> bool:
        """규칙을 제거한다."""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        return len(self._rules) < before

    def evaluate_all(self, context: dict, mode: str = "all") -> list:
        """모든 규칙을 평가하고 결과를 반환한다."""
        results = []
        for rule in self._rules:
            if rule.evaluate(context):
                actions = rule.execute(context)
                results.append({
                    "rule_id": rule.rule_id,
                    "rule_name": rule.name,
                    "matched": True,
                    "actions": actions,
                })
                if mode == "first":
                    break
        return results

    def list_rules(self) -> list:
        """규칙 목록을 반환한다."""
        return [r.to_dict() for r in self._rules]
