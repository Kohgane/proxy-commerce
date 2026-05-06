"""tests/test_pricing_rule.py — PricingRule 모델 직렬화/역직렬화 테스트 (Phase 136)."""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPricingRuleModel:
    def test_default_values(self):
        from src.pricing.rule import PricingRule
        rule = PricingRule(name="테스트 룰")
        assert rule.enabled is True
        assert rule.priority == 100
        assert rule.scope_type == "all"
        assert rule.action_kind == "notify_only"
        assert rule.dry_run is True
        assert rule.notify_threshold_pct == Decimal("10")

    def test_to_dict_round_trip(self):
        from src.pricing.rule import PricingRule
        original = PricingRule(
            name="최소 마진 가드",
            enabled=True,
            priority=10,
            scope_type="domain",
            scope_value="yoshidakaban.com",
            triggers=[{"kind": "min_margin_pct", "op": "<", "value": 15}],
            action_kind="set_margin",
            action_value=Decimal("15"),
            action_floor_krw=10000,
            action_ceiling_krw=500000,
            dry_run=True,
            notify_threshold_pct=Decimal("5"),
        )
        d = original.to_dict()
        restored = PricingRule.from_dict(d)

        assert restored.name == original.name
        assert restored.enabled == original.enabled
        assert restored.priority == original.priority
        assert restored.scope_type == original.scope_type
        assert restored.scope_value == original.scope_value
        assert restored.triggers == original.triggers
        assert restored.action_kind == original.action_kind
        assert restored.action_value == original.action_value
        assert restored.action_floor_krw == original.action_floor_krw
        assert restored.action_ceiling_krw == original.action_ceiling_krw
        assert restored.dry_run == original.dry_run
        assert restored.notify_threshold_pct == original.notify_threshold_pct

    def test_from_dict_with_string_bool(self):
        from src.pricing.rule import PricingRule
        rule = PricingRule.from_dict({
            "name": "test",
            "enabled": "True",
            "dry_run": "False",
            "priority": "50",
        })
        assert rule.enabled is True
        assert rule.dry_run is False
        assert rule.priority == 50

    def test_from_dict_empty_triggers_string(self):
        from src.pricing.rule import PricingRule
        rule = PricingRule.from_dict({
            "name": "test",
            "triggers": "[]",
        })
        assert rule.triggers == []

    def test_from_dict_triggers_json_string(self):
        from src.pricing.rule import PricingRule
        triggers = [{"kind": "stock_qty", "op": "<=", "value": 5}]
        rule = PricingRule.from_dict({
            "name": "test",
            "triggers": json.dumps(triggers),
        })
        assert rule.triggers == triggers

    def test_from_dict_none_floor_ceiling(self):
        from src.pricing.rule import PricingRule
        rule = PricingRule.from_dict({
            "name": "test",
            "action_floor_krw": "",
            "action_ceiling_krw": None,
        })
        assert rule.action_floor_krw is None
        assert rule.action_ceiling_krw is None

    def test_auto_generated_rule_id(self):
        from src.pricing.rule import PricingRule
        r1 = PricingRule(name="a")
        r2 = PricingRule(name="b")
        assert r1.rule_id != r2.rule_id
        assert len(r1.rule_id) > 0

    def test_rule_id_preserved_in_round_trip(self):
        from src.pricing.rule import PricingRule
        rule = PricingRule(name="test")
        original_id = rule.rule_id
        restored = PricingRule.from_dict(rule.to_dict())
        assert restored.rule_id == original_id
