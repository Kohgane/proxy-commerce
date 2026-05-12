from __future__ import annotations

from src.pricing.calculator import calculate_listing_price


def test_pricing_decision_prefers_actual_market_median(monkeypatch):
    monkeypatch.setenv("FALLBACK_USD_KRW", "1350")
    monkeypatch.setenv("PRICING_ACTUAL_DISCOUNT", "0.97")
    breakdown = calculate_listing_price(
        source_price=120,
        source_currency="USD",
        weight_kg=0.5,
        market="coupang",
        category="의류",
        competitor_prices_krw=[280000, 320000, 360000],
        actual_market_prices_krw=[209000, 215000, 220000],
    )
    assert breakdown.decision_source == "actual_market_median"
    assert breakdown.suggested_price == 208600
