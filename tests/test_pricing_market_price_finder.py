from __future__ import annotations

from src.pricing.market_price_finder import find_actual_market_price


def test_market_price_finder_returns_empty_without_live_sources():
    items = find_actual_market_price(
        gtin="840446254441",
        sku="MKT26Q1-HD0598-NATR-S",
        product_name="EIGHT BALL HOODIE",
        brand="MARKET",
    )
    assert items == []
