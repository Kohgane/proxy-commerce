from __future__ import annotations

from src.ai_listing.price_suggester import suggest_price


def test_ai_listing_price_suggester_includes_breakdown(monkeypatch):
    monkeypatch.setenv("PRICING_DEFAULT_WEIGHT_KG", "0.5")
    analysis = {
        "category": "의류",
        "brand": "MARKET",
        "_scraped_title": "EIGHT BALL HOODIE",
        "source_price": {"amount": "120.00", "currency": "USD"},
        "source_price_krw": 162000,
        "fx_rate": 1350,
    }
    result = suggest_price(analysis, "coupang", mode="auto")
    assert result["suggested_price_krw"] > 0
    assert "pricing_breakdown" in result
    assert "competitor_count" in result
