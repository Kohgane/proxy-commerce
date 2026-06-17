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
