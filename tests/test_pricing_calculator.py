from __future__ import annotations

from src.pricing.calculator import calculate_listing_price


def test_calculate_listing_price_usd_path(monkeypatch):
    monkeypatch.setenv("FALLBACK_USD_KRW", "1350")
    breakdown = calculate_listing_price(
        source_price=120,
        source_currency="USD",
        weight_kg=0.5,
        market="coupang",
        category="의류",
        competitor_prices_krw=[280000, 315000, 420000],
    )
    assert round(breakdown.cost_krw) == 162000
    assert breakdown.suggested_price > 0
    assert breakdown.margin_actual_pct > 0


def test_calculate_listing_price_jpy_path(monkeypatch):
    monkeypatch.setenv("FALLBACK_JPY_KRW", "9")
    breakdown = calculate_listing_price(
        source_price=1000,
        source_currency="JPY",
        weight_kg=0.3,
        market="smartstore",
        category="electronics",
        competitor_prices_krw=[],
    )
    assert round(breakdown.cost_krw) == 9000
    assert breakdown.calculated_price >= breakdown.total_landed
