from __future__ import annotations

from src.pricing.calculator import calculate_listing_price


def test_pricing_loss_warning_when_actual_market_too_low(monkeypatch):
    monkeypatch.setenv("FALLBACK_USD_KRW", "1350")
    monkeypatch.setenv("PRICING_ACTUAL_DISCOUNT", "0.97")
    monkeypatch.setenv("PRICING_LOSS_WARNING_ENABLED", "1")
    breakdown = calculate_listing_price(
        source_price=120,
        source_currency="USD",
        weight_kg=0.5,
        market="coupang",
        category="의류",
        competitor_prices_krw=[],
        actual_market_prices_krw=[209000, 215000, 220000],
    )
    assert breakdown.loss_warning is True
    assert breakdown.margin_actual_pct < 0
    assert breakdown.minimum_margin_price > breakdown.suggested_price
