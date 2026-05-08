from __future__ import annotations

from decimal import Decimal


def test_margin_guard_allows_safe_margin(monkeypatch):
    monkeypatch.setenv("PRICING_MIN_MARGIN_PCT", "15")
    from src.pricing.margin_guard import MarginGuard

    guard = MarginGuard()
    result = guard.evaluate(
        {
            "sku": "SKU-1",
            "buy_price": "50000",
            "buy_currency": "KRW",
            "marketplace_fee_pct": "10",
            "shipping_cost_krw": "3000",
            "ad_cost_krw": "1000",
        },
        Decimal("90000"),
    )

    assert result["allowed"] is True
    assert result["margin_pct"] >= 15.0


def test_margin_guard_rejects_low_margin(monkeypatch):
    monkeypatch.setenv("PRICING_MIN_MARGIN_PCT", "15")
    from src.pricing.margin_guard import MarginGuard

    guard = MarginGuard()
    result = guard.evaluate(
        {
            "sku": "SKU-2",
            "buy_price": "60000",
            "buy_currency": "KRW",
            "marketplace_fee_pct": "10",
            "shipping_cost_krw": "3000",
            "ad_cost_krw": "5000",
        },
        Decimal("70000"),
    )

    assert result["allowed"] is False
    assert "마진율" in result["reason"]
