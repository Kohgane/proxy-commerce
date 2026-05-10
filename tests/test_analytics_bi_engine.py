from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_bi_engine_build_dashboard(monkeypatch, tmp_path):
    monkeypatch.setenv("ANALYTICS_FALLBACK_PATH", str(tmp_path / "analytics_cache.jsonl"))
    from src.analytics.bi_engine import BIEngine

    engine = BIEngine()
    monkeypatch.setattr(engine, "_load_orders", lambda: [{"sell_price_krw": 1000, "sku": "A", "channel": "shop", "order_date": "2026-05-10T00:00:00+00:00"}])
    monkeypatch.setattr(engine, "_load_products", lambda: [{"sku": "A", "stock_qty": 3}])
    monkeypatch.setattr(engine, "_load_cs_stats", lambda: {"unanswered_24h": 1, "delayed_shipping": 0, "refund_rate": 0.0})

    data = engine.build_dashboard(force_refresh=True)
    assert "sales_summary" in data
    assert "top_products" in data
    assert "inventory_alerts" in data
