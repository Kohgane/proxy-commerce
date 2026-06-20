"""tests/test_collect_bulk_translate.py — 수집 이력 일괄 번역 (Phase 239, 브리프 §3)."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

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


def _fake_translator(provider="openai"):
    inst = MagicMock()
    inst.translate_product.return_value = {
        "title_ko": "번역된 제목", "description_ko": "번역된 설명", "provider": provider,
    }
    cls = MagicMock(return_value=inst)
    return cls


def test_bulk_translate_real_updates_title(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="Original Bag", seller_id="default")
    with patch("src.seller_console.ai.translator.AITranslator", _fake_translator("openai")):
        r = client.post("/seller/collect/bulk-translate", json={"item_ids": [a]})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["translated"] == 1
    row = chs._in_memory[0]
    assert row["title"] == "번역된 제목"
    assert json.loads(row["extra_json"])["title_ko"] == "번역된 제목"


def test_bulk_translate_stub_keeps_original_and_warns(client):
    """번역기 stub(키 없음) → 원문 유지 + 정직한 안내(가짜 번역 없음)."""
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="Original Bag", seller_id="default")
    with patch("src.seller_console.ai.translator.AITranslator", _fake_translator("stub")):
        r = client.post("/seller/collect/bulk-translate", json={"item_ids": [a]})
    data = r.get_json()
    assert data["ok"] is True
    assert data["translated"] == 0
    assert data["message"]  # 안내 메시지 존재
    assert chs._in_memory[0]["title"] == "Original Bag"  # 원문 유지


def test_bulk_translate_requires_ids(client):
    r = client.post("/seller/collect/bulk-translate", json={"item_ids": []})
    assert r.status_code == 400


def test_history_page_has_translate_button(client):
    rows = [{
        "id": "i1", "collected_at": "2026-06-19T12:00:00+00:00", "source": "manual",
        "domain": "x", "url": "https://x/1", "title": "Bag", "image_url": "", "price": "1",
        "currency": "USD", "status": "ok", "preview_url": "/seller/collect/preview/i1",
        "extra_json": "{}", "seller_id": "",
    }]
    with patch("src.seller_console.collect_history_store.list_items", return_value=rows), \
         patch("src.seller_console.collect_history_store.summary", return_value={"total": 1, "today": 0, "domains": 1, "by_source": {"extension": 0, "bookmarklet": 0, "manual": 1, "bulk": 0}}), \
         patch("src.seller_console.collect_history_store.distinct_domains", return_value=["x"]):
        resp = client.get("/seller/collect/history")
    html = resp.get_data(as_text=True)
    assert "bulkTranslateBtn" in html
    assert "runBulkTranslate" in html
