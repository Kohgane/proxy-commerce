"""src/rules_engine/rules_engine.py — 규칙 엔진."""
from __future__ import annotations

from .rule_set import RuleSet
from .rule import Rule


class RulesEngine:
    """규칙 엔진 오케스트레이터."""

    def __init__(self) -> None:
        self._rule_sets: dict[str, RuleSet] = {}

    def register_rule_set(self, rule_set: RuleSet) -> None:
        """규칙 집합을 등록한다."""
        self._rule_sets[rule_set.name] = rule_set

    def evaluate(self, rule_set_name: str, context: dict) -> list:
        """규칙 집합을 평가하고 결과를 반환한다."""
        rule_set = self._rule_sets.get(rule_set_name)
        if rule_set is None:
            return []
        return rule_set.evaluate_all(context)

    def list_rules(self) -> list:
        """등록된 모든 규칙을 반환한다."""
        all_rules: list[dict] = []
        for rule_set in self._rule_sets.values():
            all_rules.extend(rule_set.list_rules())
        return all_rules

    def add_rule(self, rule_set_name: str, rule: Rule) -> None:
        """규칙 집합에 규칙을 추가한다."""
        if rule_set_name not in self._rule_sets:
            self._rule_sets[rule_set_name] = RuleSet(name=rule_set_name)
        self._rule_sets[rule_set_name].add_rule(rule)
