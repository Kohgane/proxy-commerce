from __future__ import annotations

import json


def test_competitor_monitor_crud_and_monitor_now(tmp_path, monkeypatch):
    path = tmp_path / "competitor_prices.jsonl"
    monkeypatch.setenv("COMPETITOR_SCRAPE_FALLBACK_PATH", str(path))
    monkeypatch.setenv("ADAPTER_DRY_RUN", "0")

    from src.pricing.competitor_monitor import CompetitorMonitor

    monitor = CompetitorMonitor()
    target = monitor.create_target({
        "product_id": "SKU-1",
        "name": "테스트 경쟁사",
        "url": "https://www.coupang.com/vp/products/1",
    })

    monkeypatch.setattr(
        monitor,
        "_fetch_html",
        lambda url: '<meta property="product:price:amount" content="12000"><div>배송비 2500원</div><div>재고 있음</div>',
    )

    result = monitor.monitor_now(competitor_id=target.competitor_id)
    assert result["captured"] == 1

    history = monitor.get_history(competitor_id=target.competitor_id)
    assert history
    assert int(history[0]["price_krw"]) == 12000


def test_competitor_monitor_alert_threshold(tmp_path, monkeypatch):
    path = tmp_path / "competitor_prices.jsonl"
    monkeypatch.setenv("COMPETITOR_SCRAPE_FALLBACK_PATH", str(path))
    monkeypatch.setenv("PRICING_NOTIFY_THRESHOLD_PCT", "5")

    from src.pricing.competitor_monitor import CompetitorMonitor

    monitor = CompetitorMonitor()
    t = monitor.create_target({"product_id": "SKU-1", "name": "x", "url": "https://www.coupang.com/vp/products/2"})

    htmls = [
        '<meta property="product:price:amount" content="10000">',
        '<meta property="product:price:amount" content="9000">',
    ]
    monkeypatch.setattr(monitor, "_fetch_html", lambda url: htmls.pop(0))

    called = []
    monkeypatch.setattr(monitor, "_send_price_alert", lambda *args, **kwargs: called.append(True) or True)

    monitor.monitor_now(competitor_id=t.competitor_id)
    monitor.monitor_now(competitor_id=t.competitor_id)

    assert called, "변동 임계 초과 시 알림이 발생해야 함"
