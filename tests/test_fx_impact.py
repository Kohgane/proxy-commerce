from __future__ import annotations


def test_fx_impact_filters_impacted_products(monkeypatch):
    from src.pricing.fx_impact import FXImpactAnalyzer

    analyzer = FXImpactAnalyzer(alert_threshold_pct=2)
    monkeypatch.setattr(analyzer, "daily_changes", lambda: {"USD": 2.5, "JPY": 0.4, "CNY": -2.2})

    impacted = analyzer.impacted_products(
        [
            {"sku": "A", "buy_currency": "USD", "sell_price_krw": 10000},
            {"sku": "B", "buy_currency": "JPY", "sell_price_krw": 10000},
            {"sku": "C", "buy_currency": "CNY", "sell_price_krw": 10000},
        ]
    )

    skus = {x["sku"] for x in impacted}
    assert skus == {"A", "C"}


def test_fx_impact_detect_and_notify(monkeypatch):
    from src.pricing.fx_impact import FXImpactAnalyzer

    analyzer = FXImpactAnalyzer(alert_threshold_pct=2)
    monkeypatch.setattr(analyzer, "daily_changes", lambda: {"USD": 2.1, "JPY": 0, "CNY": 0})
    monkeypatch.setattr(analyzer, "impacted_products", lambda catalog_rows=None: [{"sku": "A"}])

    calls = []
    monkeypatch.setattr(analyzer, "_notify", lambda alerts, impacted_count: calls.append((alerts, impacted_count)))

    result = analyzer.detect_and_notify()
    assert len(result["alerts"]) == 1
    assert calls and calls[0][1] == 1
