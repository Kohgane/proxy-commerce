"""tests/test_collect_bulk_price.py — 수집 이력 일괄 가격/마진 (Phase 240, 브리프 §3)."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_store():
    from src.seller_console import collect_history_store as chs
    chs._in_memory.clear()
    yield
    chs._in_memory.clear()


def test_bulk_margin_stored_in_extra(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="t", price="100", seller_id="default")
    r = client.post("/seller/collect/bulk-price", json={"item_ids": [a], "target_margin_pct": 30})
    assert r.status_code == 200
    assert r.get_json()["updated"] == 1
    assert json.loads(chs._in_memory[0]["extra_json"])["target_margin_pct"] == 30.0


def test_bulk_price_multiplier_applies(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="t", price="100", seller_id="default")
    r = client.post("/seller/collect/bulk-price", json={"item_ids": [a], "price_multiplier": 1.1})
    assert r.status_code == 200
    assert chs._in_memory[0]["price"] == "110.0"


def test_bulk_price_non_numeric_skips_price_but_margin_ok(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="t", price="문의", seller_id="default")
    r = client.post("/seller/collect/bulk-price",
                    json={"item_ids": [a], "target_margin_pct": 20, "price_multiplier": 2})
    assert r.status_code == 200
    row = chs._in_memory[0]
    assert row["price"] == "문의"  # 비숫자 → 가격 그대로
    assert json.loads(row["extra_json"])["target_margin_pct"] == 20.0  # 마진은 적용


def test_bulk_price_requires_one_field(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="t", price="100", seller_id="default")
    r = client.post("/seller/collect/bulk-price", json={"item_ids": [a]})
    assert r.status_code == 400


def test_bulk_price_validates_ranges(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="t", price="100", seller_id="default")
    assert client.post("/seller/collect/bulk-price", json={"item_ids": [a], "target_margin_pct": 99}).status_code == 400
    assert client.post("/seller/collect/bulk-price", json={"item_ids": [a], "price_multiplier": -1}).status_code == 400


def test_history_page_has_price_button(client):
    rows = [{
        "id": "i1", "collected_at": "2026-06-19T12:00:00+00:00", "source": "manual",
        "domain": "x", "url": "https://x/1", "title": "t", "image_url": "", "price": "1",
        "currency": "USD", "status": "ok", "preview_url": "/seller/collect/preview/i1",
        "extra_json": "{}", "seller_id": "",
    }]
    with patch("src.seller_console.collect_history_store.list_items", return_value=rows), \
         patch("src.seller_console.collect_history_store.summary", return_value={"total": 1, "today": 0, "domains": 1, "by_source": {"extension": 0, "bookmarklet": 0, "manual": 1, "bulk": 0}}), \
         patch("src.seller_console.collect_history_store.distinct_domains", return_value=["x"]):
        html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "bulkPriceBtn" in html
    assert "runBulkPrice" in html
