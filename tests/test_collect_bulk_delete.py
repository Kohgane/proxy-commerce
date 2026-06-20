"""tests/test_collect_bulk_delete.py — 수집 이력 일괄 삭제 (Phase 237, 브리프 §3)."""
from __future__ import annotations

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


def _seed(chs, n=3, seller="s1"):
    ids = []
    for i in range(n):
        ids.append(chs.append(source="manual", url=f"https://x/{i}", title=f"item{i}", seller_id=seller))
    return ids


def test_store_delete_removes_only_selected_and_seller_isolated():
    from src.seller_console import collect_history_store as chs
    a, b, c = _seed(chs, 3, seller="s1")
    other = chs.append(source="manual", url="https://x/o", title="other", seller_id="s2")
    # s1이 a,b 삭제 — c와 타 셀러 other는 유지
    deleted = chs.delete([a, b], seller_id="s1")
    assert deleted == 2
    remaining_ids = {r["id"] for r in chs._in_memory}
    assert a not in remaining_ids and b not in remaining_ids
    assert c in remaining_ids and other in remaining_ids


def test_store_delete_seller_isolation_blocks_other_seller():
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="x", seller_id="s1")
    # 다른 셀러는 삭제 못 함
    assert chs.delete([a], seller_id="s2") == 0
    assert any(r["id"] == a for r in chs._in_memory)


def test_bulk_delete_route_requires_ids(client):
    r = client.post("/seller/collect/bulk-delete", json={"item_ids": []})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_bulk_delete_route_deletes(client):
    from src.seller_console import collect_history_store as chs
    ids = _seed(chs, 3, seller="default")  # _seller_id() 기본값
    r = client.post("/seller/collect/bulk-delete", json={"item_ids": ids[:2]})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["deleted"] == 2


def test_history_page_has_bulk_delete_button(client):
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
    assert "bulkDeleteBtn" in html
    assert "runBulkDelete" in html
