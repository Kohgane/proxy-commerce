from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_pricing_rule_store_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICING_RULES_FALLBACK_PATH", str(tmp_path / "pricing_rules.jsonl"))
    from src.pricing.rule import PricingRule, PricingRuleStore

    store = PricingRuleStore()
    created = store.create(PricingRule(name="유지 테스트"))
    store2 = PricingRuleStore()
    rules = store2.list_all()
    assert any(r.rule_id == created.rule_id for r in rules)
