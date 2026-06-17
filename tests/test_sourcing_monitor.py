"""tests/test_sourcing_monitor.py — 수집상품 소싱처 변화 모니터링 (가격/품절/옵션)."""
from __future__ import annotations

import os
import sys
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _sp(price=None, in_stock=None, options=None, currency="USD", method="jsonld"):
    return SimpleNamespace(price=price, in_stock=in_stock, options=options or {},
                           currency=currency, extraction_method=method)


def _item(price="100", url="https://brand.example/p/1", options=None):
    extra = {"price_original": price, "options": options or {}}
    return {"id": "it1", "url": url, "price": price, "currency": "USD",
            "title": "샘플", "extra_json": json.dumps(extra)}


def test_change_price_up_detected():
    from src.seller_console import views
    with patch("src.collectors.universal_scraper.UniversalScraper") as M:
        M.return_value.fetch.return_value = _sp(price=130, in_stock=True)
        mon = views._check_source_change(_item(price="100"))
    assert mon["change"] == "price"
    assert "가격" in mon["summary"] and "▲" in mon["summary"]


def test_change_out_of_stock_detected():
    from src.seller_console import views
    with patch("src.collectors.universal_scraper.UniversalScraper") as M:
        M.return_value.fetch.return_value = _sp(price=100, in_stock=False)
        mon = views._check_source_change(_item(price="100"))
    assert mon["change"] == "out_of_stock"
    assert "품절" in mon["summary"]


def test_change_none_when_same():
    from src.seller_console import views
    with patch("src.collectors.universal_scraper.UniversalScraper") as M:
        M.return_value.fetch.return_value = _sp(price=100, in_stock=True)
        mon = views._check_source_change(_item(price="100"))
    assert mon["change"] == "none"
    assert mon["summary"] == "변화 없음"


def test_unfetchable_is_honest_not_fake():
    from src.seller_console import views
    with patch("src.collectors.universal_scraper.UniversalScraper") as M:
        M.return_value.fetch.return_value = _sp(price=None, in_stock=None)
        mon = views._check_source_change(_item(price="100"))
    assert mon["change"] == "unknown"
    assert "확인 불가" in mon["summary"]


def test_option_size_change_detected():
    from src.seller_console import views
    with patch("src.collectors.universal_scraper.UniversalScraper") as M:
        M.return_value.fetch.return_value = _sp(price=100, in_stock=True, options={"size": ["S", "M"]})
        mon = views._check_source_change(_item(price="100", options={"size": ["S", "M", "L"]}))
    assert mon["change"] in ("options", "changed")
    assert "옵션" in mon["summary"] or "사이즈" in mon["summary"]


def test_monitor_check_endpoint(client):
    from src.seller_console import views
    item = _item(price="100")
    with patch("src.seller_console.collect_history_store.get", return_value=item), \
         patch("src.seller_console.collect_history_store.update", return_value=True), \
         patch.object(views, "_check_source_change", return_value={"change": "price", "summary": "가격 ▲", "checked_at": "2026-06-17T00:00:00"}):
        resp = client.post("/seller/sourcing/monitor/check", json={"item_id": "it1"})
    data = resp.get_json()
    assert data["ok"] is True
    assert data["results"][0]["change"] == "price"


def test_monitor_page_renders(client):
    with patch("src.seller_console.collect_history_store.list_items", return_value=[_item(price="100")]):
        resp = client.get("/seller/sourcing/monitor")
    assert resp.status_code == 200
    assert "소싱처 변화 모니터링" in resp.get_data(as_text=True)


# 자동확인 — 배치 러너 + cron 엔드포인트
def test_run_auto_monitor_skips_recent_and_counts_changes():
    from src.seller_console import views
    from datetime import datetime, timezone, timedelta
    recent = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    fresh_item = {"id": "fresh", "url": "https://x/1", "price": "100", "currency": "USD",
                  "extra_json": json.dumps({"monitor": {"checked_at": recent, "change": "none"}})}
    stale_item = {"id": "stale", "url": "https://x/2", "price": "100", "currency": "USD",
                  "extra_json": json.dumps({"monitor": {"checked_at": old, "change": "none"}, "price_original": "100"})}
    with patch("src.seller_console.collect_history_store.list_items", return_value=[fresh_item, stale_item]), \
         patch("src.seller_console.collect_history_store.update", return_value=True), \
         patch.object(views, "_check_source_change", return_value={"change": "price", "summary": "가격 ▲", "checked_at": "2026-06-17T00:00:00"}):
        summary = views.run_auto_source_monitor(only_stale_hours=6)
    assert summary["skipped"] == 1      # fresh 건너뜀
    assert summary["checked"] == 1      # stale 확인
    assert summary["changed"] == 1
    assert summary["alerts"][0]["id"] == "stale"


def test_cron_sourcing_monitor_route(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    with patch("src.seller_console.views.run_auto_source_monitor",
               return_value={"total": 3, "checked": 2, "changed": 1, "skipped": 1, "alerts": []}):
        resp = client.post("/cron/sourcing-monitor")
    data = resp.get_json()
    assert resp.status_code == 200 and data["ok"] is True
    assert data["checked"] == 2 and data["changed"] == 1


def test_cron_sourcing_monitor_requires_secret(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    resp = client.post("/cron/sourcing-monitor")  # 헤더 없음 → 401
    assert resp.status_code == 401
