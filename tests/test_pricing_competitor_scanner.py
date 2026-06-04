from __future__ import annotations

from src.pricing.competitor_scanner import _filter_iqr, scan_competitor_prices


def test_competitor_scanner_returns_empty_without_verified_data():
    items = scan_competitor_prices(product_name="EIGHT BALL HOODIE", brand="MARKET", market="smartstore", limit=5)
    assert items == []


def test_competitor_scanner_iqr_filters_outliers():
    rows = [
        {"price_krw": 100000},
        {"price_krw": 102000},
        {"price_krw": 103000},
        {"price_krw": 101500},
        {"price_krw": 9999999},
    ]
    filtered = _filter_iqr(rows)
    assert len(filtered) == 4
