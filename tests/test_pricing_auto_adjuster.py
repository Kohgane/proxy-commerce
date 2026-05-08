from __future__ import annotations

from decimal import Decimal


class _Rule:
    def __init__(self, action_kind: str, action_value: str, floor=None, ceil=None):
        self.rule_id = "r1"
        self.name = "rule"
        self.action_kind = action_kind
        self.action_value = Decimal(action_value)
        self.action_floor_krw = floor
        self.action_ceiling_krw = ceil


class _Store:
    def __init__(self, rules):
        self._rules = rules

    def active_sorted(self):
        return self._rules


def test_auto_adjuster_match_lowest_dry_run(monkeypatch):
    monkeypatch.setenv("PRICING_AUTO_APPLY", "0")
    from src.pricing.auto_adjuster import PricingAutoAdjuster

    adjuster = PricingAutoAdjuster()
    monkeypatch.setattr(adjuster, "_get_catalog_rows", lambda: [{"sku": "SKU-1", "sell_price_krw": 10000, "buy_price": 6000, "buy_currency": "KRW"}])

    import src.pricing.rule as rule_mod
    monkeypatch.setattr(rule_mod, "PricingRuleStore", lambda: _Store([_Rule("match_lowest", "-3")]))

    import src.pricing.competitor_monitor as cm_mod
    monkeypatch.setattr(cm_mod.CompetitorMonitor, "get_lowest_price", lambda self, product_id: Decimal("9500"))

    res = adjuster.evaluate(dry_run=True)
    assert res["changed"] == 1
    assert res["details"][0]["auto_applied"] is False


def test_auto_adjuster_auto_apply_guard(monkeypatch):
    monkeypatch.setenv("PRICING_AUTO_APPLY", "1")
    monkeypatch.setenv("PRICING_AUTO_APPLY_THRESHOLD_PCT", "5")
    from src.pricing.auto_adjuster import PricingAutoAdjuster

    adjuster = PricingAutoAdjuster()
    monkeypatch.setattr(adjuster, "_get_catalog_rows", lambda: [{"sku": "SKU-2", "sell_price_krw": 10000, "buy_price": 6000, "buy_currency": "KRW"}])

    import src.pricing.rule as rule_mod
    monkeypatch.setattr(rule_mod, "PricingRuleStore", lambda: _Store([_Rule("add", "300")]))

    res = adjuster.evaluate(dry_run=False)
    assert res["changed"] == 1
    assert res["applied"] == 1
