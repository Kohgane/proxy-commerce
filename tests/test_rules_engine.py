"""tests/test_rules_engine.py — Phase 69 규칙 엔진 테스트."""
from __future__ import annotations

import pytest
from src.rules_engine.condition import ComparisonCondition, CompositeCondition, TimeCondition
from src.rules_engine.action import NotifyAction, UpdateFieldAction, AssignAction
from src.rules_engine.rule import Rule
from src.rules_engine.rule_set import RuleSet
from src.rules_engine.rules_engine import RulesEngine


class TestCondition:
    def test_comparison_gt(self):
        c = ComparisonCondition(field="score", operator="gt", value=5)
        assert c.evaluate({"score": 10}) is True
        assert c.evaluate({"score": 3}) is False

    def test_comparison_eq(self):
        c = ComparisonCondition(field="status", operator="eq", value="active")
        assert c.evaluate({"status": "active"}) is True
        assert c.evaluate({"status": "inactive"}) is False

    def test_comparison_in(self):
        c = ComparisonCondition(field="category", operator="in", value=["A", "B"])
        assert c.evaluate({"category": "A"}) is True
        assert c.evaluate({"category": "C"}) is False

    def test_comparison_contains(self):
        c = ComparisonCondition(field="name", operator="contains", value="hello")
        assert c.evaluate({"name": "say hello world"}) is True
        assert c.evaluate({"name": "bye"}) is False

    def test_composite_and(self):
        c1 = ComparisonCondition(field="a", operator="gt", value=0)
        c2 = ComparisonCondition(field="b", operator="lt", value=10)
        comp = CompositeCondition(operator="AND", conditions=[c1, c2])
        assert comp.evaluate({"a": 1, "b": 5}) is True
        assert comp.evaluate({"a": -1, "b": 5}) is False

    def test_composite_or(self):
        c1 = ComparisonCondition(field="a", operator="eq", value=1)
        c2 = ComparisonCondition(field="b", operator="eq", value=2)
        comp = CompositeCondition(operator="OR", conditions=[c1, c2])
        assert comp.evaluate({"a": 1, "b": 99}) is True
        assert comp.evaluate({"a": 99, "b": 99}) is False

    def test_composite_not(self):
        c = ComparisonCondition(field="x", operator="eq", value=0)
        comp = CompositeCondition(operator="NOT", conditions=[c])
        assert comp.evaluate({"x": 1}) is True
        assert comp.evaluate({"x": 0}) is False

    def test_time_condition_weekends(self):
        tc = TimeCondition(condition_type="weekends")
        result = tc.evaluate({})
        assert isinstance(result, bool)


class TestAction:
    def test_notify_action(self):
        a = NotifyAction(message="알림!")
        result = a.execute({})
        assert result["action"] == "notify"
        assert result["message"] == "알림!"

    def test_update_field_action(self):
        a = UpdateFieldAction(field="status", value="closed")
        result = a.execute({})
        assert result["action"] == "update_field"
        assert result["field"] == "status"
        assert result["value"] == "closed"

    def test_assign_action(self):
        a = AssignAction(assignee="user123")
        result = a.execute({})
        assert result["action"] == "assign"
        assert result["assignee"] == "user123"


class TestRule:
    def test_rule_evaluate_true(self):
        cond = ComparisonCondition(field="amount", operator="gt", value=1000)
        action = NotifyAction(message="큰 주문!")
        rule = Rule(name="big_order", conditions=[cond], actions=[action])
        assert rule.evaluate({"amount": 5000}) is True

    def test_rule_evaluate_false(self):
        cond = ComparisonCondition(field="amount", operator="gt", value=1000)
        action = NotifyAction(message="큰 주문!")
        rule = Rule(name="big_order", conditions=[cond], actions=[action])
        assert rule.evaluate({"amount": 100}) is False

    def test_rule_disabled(self):
        cond = ComparisonCondition(field="x", operator="eq", value=1)
        rule = Rule(name="r", conditions=[cond], actions=[], enabled=False)
        assert rule.evaluate({"x": 1}) is False

    def test_rule_execute(self):
        cond = ComparisonCondition(field="x", operator="eq", value=1)
        action = NotifyAction(message="msg")
        rule = Rule(name="r", conditions=[cond], actions=[action])
        results = rule.execute({"x": 1})
        assert len(results) == 1
        assert results[0]["action"] == "notify"

    def test_rule_to_dict(self):
        rule = Rule(name="test", conditions=[], actions=[])
        d = rule.to_dict()
        assert "rule_id" in d
        assert d["name"] == "test"


class TestRuleSet:
    def test_add_remove_rule(self):
        rs = RuleSet("test")
        cond = ComparisonCondition(field="x", operator="eq", value=1)
        rule = Rule(name="r", conditions=[cond], actions=[])
        rs.add_rule(rule)
        assert len(rs.list_rules()) == 1
        rs.remove_rule(rule.rule_id)
        assert len(rs.list_rules()) == 0

    def test_evaluate_all(self):
        rs = RuleSet("test")
        cond = ComparisonCondition(field="x", operator="eq", value=1)
        action = NotifyAction(message="match")
        rule = Rule(name="r", conditions=[cond], actions=[action])
        rs.add_rule(rule)
        results = rs.evaluate_all({"x": 1})
        assert len(results) == 1
        assert results[0]["matched"] is True

    def test_evaluate_all_no_match(self):
        rs = RuleSet("test")
        cond = ComparisonCondition(field="x", operator="eq", value=99)
        rule = Rule(name="r", conditions=[cond], actions=[])
        rs.add_rule(rule)
        results = rs.evaluate_all({"x": 1})
        assert results == []


class TestRulesEngine:
    def test_evaluate_missing_rule_set(self):
        engine = RulesEngine()
        result = engine.evaluate("nonexistent", {})
        assert result == []

    def test_register_and_evaluate(self):
        engine = RulesEngine()
        rs = RuleSet("default")
        cond = ComparisonCondition(field="status", operator="eq", value="new")
        action = NotifyAction(message="새 주문!")
        rule = Rule(name="new_order", conditions=[cond], actions=[action])
        rs.add_rule(rule)
        engine.register_rule_set(rs)
        results = engine.evaluate("default", {"status": "new"})
        assert len(results) == 1

    def test_list_rules_empty(self):
        engine = RulesEngine()
        assert engine.list_rules() == []

    def test_list_rules(self):
        engine = RulesEngine()
        engine.add_rule("test", Rule(name="r1", conditions=[], actions=[]))
        engine.add_rule("test", Rule(name="r2", conditions=[], actions=[]))
        rules = engine.list_rules()
        assert len(rules) == 2
