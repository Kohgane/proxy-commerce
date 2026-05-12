from __future__ import annotations


def test_convert_to_krw_uses_fallback_env(monkeypatch):
    from src.ai_listing.jsonld_parser import convert_to_krw

    monkeypatch.setenv("FX_USDKRW", "1375")
    converted = convert_to_krw("120.00", "USD")
    assert converted["amount_krw"] == 165000
    assert str(converted["rate"]) == "1375"


def test_convert_to_krw_supports_jpy(monkeypatch):
    from src.ai_listing.jsonld_parser import convert_to_krw

    monkeypatch.setenv("FX_JPYKRW", "9.2")
    converted = convert_to_krw("1000", "JPY")
    assert converted["amount_krw"] == 9200
