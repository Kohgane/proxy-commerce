"""tests/test_collect_bulk_status_duplicate.py — 일괄 상태변경/복제 (Phase 241, 브리프 §3)."""
from __future__ import annotations

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


def test_bulk_status_archive(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="t", seller_id="default")
    r = client.post("/seller/collect/bulk-status", json={"item_ids": [a], "status": "archived"})
    assert r.status_code == 200
    assert r.get_json()["updated"] == 1
    assert chs._in_memory[0]["status"] == "archived"


def test_bulk_status_rejects_bad_value(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="t", seller_id="default")
    r = client.post("/seller/collect/bulk-status", json={"item_ids": [a], "status": "deleted"})
    assert r.status_code == 400


def test_bulk_duplicate_creates_copies(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="가방", price="100", seller_id="default")
    before = len(chs._in_memory)
    r = client.post("/seller/collect/bulk-duplicate", json={"item_ids": [a]})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True and data["duplicated"] == 1
    assert len(chs._in_memory) == before + 1
    titles = [row["title"] for row in chs._in_memory]
    assert any("(복제)" in t for t in titles)


def test_bulk_duplicate_requires_ids(client):
    r = client.post("/seller/collect/bulk-duplicate", json={"item_ids": []})
    assert r.status_code == 400


def test_history_page_has_status_and_duplicate_buttons(client):
    rows = [{
        "id": "i1", "collected_at": "2026-06-19T12:00:00+00:00", "source": "manual",
        "domain": "x", "url": "https://x/1", "title": "t", "image_url": "", "price": "1",
        "currency": "USD", "status": "archived", "preview_url": "/seller/collect/preview/i1",
        "extra_json": "{}", "seller_id": "",
    }]
    with patch("src.seller_console.collect_history_store.list_items", return_value=rows), \
         patch("src.seller_console.collect_history_store.summary", return_value={"total": 1, "today": 0, "domains": 1, "by_source": {"extension": 0, "bookmarklet": 0, "manual": 1, "bulk": 0}}), \
         patch("src.seller_console.collect_history_store.distinct_domains", return_value=["x"]):
        html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "bulkStatusBtn" in html and "bulkDuplicateBtn" in html
    assert "runBulkDuplicate" in html
    assert "📦 보관" in html  # archived 배지 렌더
