from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_rule(name: str, priority: int = 10):
    from src.pricing.rule import PricingRule

    return PricingRule(
        name=name,
        priority=priority,
        action_kind="multiply",
        action_value=Decimal("1.05"),
    )


def test_create_then_list_across_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICING_RULES_FALLBACK_PATH", str(tmp_path / "rules.jsonl"))
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)

    from src.pricing.rule import PricingRuleStore

    store_a = PricingRuleStore()
    store_a.create(_make_rule("테스트 룰", 10))

    store_b = PricingRuleStore()
    rules = store_b.list_all()

    assert len(rules) == 1
    assert rules[0].name == "테스트 룰"


def test_update_visible_across_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICING_RULES_FALLBACK_PATH", str(tmp_path / "rules.jsonl"))
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)

    from src.pricing.rule import PricingRuleStore

    store_a = PricingRuleStore()
    created = store_a.create(_make_rule("원본 룰", 10))

    store_b = PricingRuleStore()
    created.name = "수정된 룰"
    assert store_b.update(created) is True

    store_c = PricingRuleStore()
    rules = store_c.list_all()
    assert len(rules) == 1
    assert rules[0].name == "수정된 룰"


def test_delete_visible_across_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICING_RULES_FALLBACK_PATH", str(tmp_path / "rules.jsonl"))
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)

    from src.pricing.rule import PricingRuleStore

    store_a = PricingRuleStore()
    created = store_a.create(_make_rule("삭제 대상", 10))

    store_b = PricingRuleStore()
    assert store_b.delete(created.rule_id) is True

    store_c = PricingRuleStore()
    assert store_c.list_all() == []


def test_concurrent_create_uses_lock_safely(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICING_RULES_FALLBACK_PATH", str(tmp_path / "rules.jsonl"))
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)

    from src.pricing.rule import PricingRuleStore

    def _create_one(i: int):
        PricingRuleStore().create(_make_rule(f"룰-{i}", i))

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(_create_one, range(12)))

    listed = PricingRuleStore().list_all()
    assert len(listed) == 12
    assert {r.name for r in listed} == {f"룰-{i}" for i in range(12)}
