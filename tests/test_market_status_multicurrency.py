from __future__ import annotations

from src.seller_console.market_status import (
    MarketStatusItem,
    convert_amount,
    format_currency_amount,
    marketplace_meta,
)


def test_market_status_item_price_krw_backward_compatible():
    item = MarketStatusItem(marketplace="coupang", product_id="P1", state="active", price_krw=12300)
    assert item.price == 12300
    assert item.currency == "KRW"
    assert item.price_krw == 12300


def test_market_status_item_usd_to_krw_conversion(monkeypatch):
    monkeypatch.setenv("FX_USDKRW", "1400")
    item = MarketStatusItem(marketplace="amazon", product_id="P2", state="active", price=10, currency="USD")
    assert item.price_krw == 14000


def test_convert_amount_unavailable_rate_returns_false():
    amount, ok = convert_amount(10, "SGD", "KRW")
    assert ok is False
    assert amount is None


def test_format_currency_amount_jpy_has_no_decimals():
    assert format_currency_amount(1234.56, "JPY") == "¥1,235"


def test_marketplace_meta_contains_global_fields():
    meta = marketplace_meta("ebay")
    assert meta["country"] == "GB"
    assert meta["currency"] == "GBP"
    assert meta["locale"] == "en-GB"
