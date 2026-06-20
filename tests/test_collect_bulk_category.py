"""tests/test_collect_bulk_category.py — 수집 이력 일괄 카테고리 지정 (Phase 238, 브리프 §3)."""
from __future__ import annotations

import json
import os
import sys

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


def test_bulk_category_explicit_code(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="무지 티셔츠", seller_id="default")
    b = chs.append(source="manual", url="https://x/2", title="아무거나", seller_id="default")
    r = client.post("/seller/collect/bulk-category", json={"item_ids": [a, b], "category_code": "CLO"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True and data["updated"] == 2
    for it in chs._in_memory:
        assert json.loads(it["extra_json"])["category_code"] == "CLO"


def test_bulk_category_auto_classifies_by_title(client):
    from src.seller_console import collect_history_store as chs
    bag = chs.append(source="manual", url="https://x/1", title="크로스백 가방", seller_id="default")
    r = client.post("/seller/collect/bulk-category", json={"item_ids": [bag], "auto": True})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    code = json.loads(chs._in_memory[0]["extra_json"])["category_code"]
    assert code == "BAG"


def test_bulk_category_requires_code_or_auto(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="x", seller_id="default")
    r = client.post("/seller/collect/bulk-category", json={"item_ids": [a]})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_bulk_category_requires_ids(client):
    r = client.post("/seller/collect/bulk-category", json={"item_ids": [], "category_code": "BAG"})
    assert r.status_code == 400


def test_history_page_has_bulk_category_ui(client):
    from unittest.mock import patch
    rows = [{
        "id": "i1", "collected_at": "2026-06-19T12:00:00+00:00", "source": "manual",
        "domain": "x", "url": "https://x/1", "title": "가방", "image_url": "", "price": "1",
        "currency": "USD", "status": "ok", "preview_url": "/seller/collect/preview/i1",
        "extra_json": "{}", "seller_id": "",
    }]
    with patch("src.seller_console.collect_history_store.list_items", return_value=rows), \
         patch("src.seller_console.collect_history_store.summary", return_value={"total": 1, "today": 0, "domains": 1, "by_source": {"extension": 0, "bookmarklet": 0, "manual": 1, "bulk": 0}}), \
         patch("src.seller_console.collect_history_store.distinct_domains", return_value=["x"]):
        resp = client.get("/seller/collect/history")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "bulkCategoryBtn" in html
    assert "runBulkCategory" in html
    assert "자동 분류" in html
