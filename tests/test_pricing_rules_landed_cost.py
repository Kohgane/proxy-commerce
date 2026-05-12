from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from src.pricing.engine import PricingEngine


def test_engine_supports_landed_cost_margin_action():
    engine = PricingEngine()
    rule = SimpleNamespace(action_kind="landed_cost_margin", action_value=Decimal("30"))
    price = engine._apply_action(rule, {"buy_price": 100, "buy_currency": "USD"}, Decimal("1000"), {"USDKRW": 1000})
    assert price > 0


def test_engine_supports_competitor_minus_pct_action(monkeypatch):
    engine = PricingEngine()
    monkeypatch.setattr(engine, "_get_competitor_min_price", lambda sku: Decimal("300000"))
    rule = SimpleNamespace(action_kind="competitor_minus_pct", action_value=Decimal("3"))
    price = engine._apply_action(rule, {"sku": "SKU-1"}, Decimal("1000"), {})
    assert price == Decimal("291000")
