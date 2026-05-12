from __future__ import annotations

from src.pricing.competitor_scanner import _filter_iqr, scan_competitor_prices


def test_competitor_scanner_mock_returns_items():
    items = scan_competitor_prices(product_name="EIGHT BALL HOODIE", brand="MARKET", market="smartstore", limit=5)
    assert len(items) == 5
    assert all("price_krw" in i for i in items)


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
