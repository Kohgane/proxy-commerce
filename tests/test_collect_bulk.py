"""tests/test_collect_bulk.py — 여러 URL 일괄 수집(③) 검증."""
from __future__ import annotations

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


def _fake_draft(title="샘플", url="https://x"):
    return {
        "title_ko": title, "title": title, "title_en": title, "price_original": 19.9,
        "currency": "USD", "images": ["https://img/1.jpg"], "url": url, "is_mock": False,
    }


def test_bulk_empty_returns_400(client):
    resp = client.post("/seller/collect/bulk", json={"urls": ""})
    assert resp.status_code == 400


def test_bulk_collects_and_saves_to_history(client):
    with patch("src.seller_console.views._collect_real_draft", side_effect=lambda url, **k: _fake_draft(url=url)), \
         patch("src.seller_console.collect_history_store.append", return_value="abc123") as mock_append:
        resp = client.post("/seller/collect/bulk", json={
            "urls": "https://www.amazon.com/dp/B1\nhttps://item.taobao.com/2"})
    data = resp.get_json()
    assert data["ok"] is True
    assert data["total"] == 2
    assert data["success"] == 2
    assert all(r["ok"] and r["preview_url"] for r in data["results"])
    assert mock_append.call_count == 2


def test_bulk_rejects_non_http_and_dedupes(client):
    with patch("src.seller_console.views._collect_real_draft", side_effect=lambda url, **k: _fake_draft(url=url)), \
         patch("src.seller_console.collect_history_store.append", return_value="x"):
        resp = client.post("/seller/collect/bulk", json={
            "urls": "ftp://bad\nhttps://ok.com/a\nhttps://ok.com/a"})  # 비http + 중복
    data = resp.get_json()
    # 중복 제거 → 2개(ftp, ok), ftp는 실패
    assert data["total"] == 2
    by_ok = {r["ok"] for r in data["results"]}
    assert False in by_ok and True in by_ok


def test_bulk_per_url_error_isolated(client):
    def _collect(url, **k):
        if "bad" in url:
            raise RuntimeError("extract fail")
        return _fake_draft(url=url)
    with patch("src.seller_console.views._collect_real_draft", side_effect=_collect), \
         patch("src.seller_console.collect_history_store.append", return_value="x"):
        resp = client.post("/seller/collect/bulk", json={
            "urls": "https://good.com/1\nhttps://bad.com/2"})
    data = resp.get_json()
    assert data["success"] == 1
    assert data["total"] == 2


def test_bulk_no_mock_on_extract_failure(client):
    """실 추출 실패(None) 시 목업 없이 실패로 기록 (Phase 203)."""
    with patch("src.seller_console.views._collect_real_draft", return_value=None), \
         patch("src.seller_console.collect_history_store.append") as mock_append:
        resp = client.post("/seller/collect/bulk", json={"urls": "https://blocked.com/1"})
    data = resp.get_json()
    assert data["total"] == 1
    assert data["success"] == 0
    assert data["results"][0]["ok"] is False
    mock_append.assert_not_called()


# ─── ④ 일괄 업로드 ────────────────────────────────────────────────────────────

def test_bulk_upload_requires_items_and_markets(client):
    assert client.post("/seller/collect/bulk-upload", json={"item_ids": [], "markets": ["shopify"]}).status_code == 400
    assert client.post("/seller/collect/bulk-upload", json={"item_ids": ["a"], "markets": []}).status_code == 400


def test_bulk_upload_dispatches_per_item(client):
    disp = MagicMock()
    dr = MagicMock()
    dr.succeeded = 1
    dr.to_dict.return_value = {"succeeded": 1, "failed": 0, "results": []}
    disp.dispatch.return_value = dr
    item = {"title": "샘플", "extra_json": '{"title":"샘플","sell_price_krw":19900}'}
    with patch("src.seller_console.views._get_upload_dispatcher", return_value=disp), \
         patch("src.seller_console.collect_history_store.get", return_value=item):
        resp = client.post("/seller/collect/bulk-upload", json={
            "item_ids": ["id1", "id2"], "markets": ["shopify", "coupang"], "target_margin_pct": 25})
    data = resp.get_json()
    assert data["ok"] is True
    assert data["total"] == 2
    assert data["succeeded"] == 2
    assert disp.dispatch.call_count == 2
    # 마진율이 product에 주입됐는지
    called_product = disp.dispatch.call_args.args[0]
    assert called_product.get("target_margin_pct") == 25.0


def test_bulk_upload_missing_item_isolated(client):
    disp = MagicMock()
    dr = MagicMock()
    dr.succeeded = 1
    dr.to_dict.return_value = {"succeeded": 1}
    disp.dispatch.return_value = dr

    def _get(item_id, seller_id=None):
        return None if item_id == "missing" else {"title": "ok", "extra_json": "{}"}
    with patch("src.seller_console.views._get_upload_dispatcher", return_value=disp), \
         patch("src.seller_console.collect_history_store.get", side_effect=_get):
        resp = client.post("/seller/collect/bulk-upload", json={
            "item_ids": ["good", "missing"], "markets": ["shopify"]})
    data = resp.get_json()
    assert data["total"] == 2
    assert data["succeeded"] == 1
    by_ok = {r["ok"] for r in data["results"]}
    assert False in by_ok and True in by_ok


# Phase 215: /collect/preview save=true → 수집 이력 저장 + 위치 링크 반환
def test_preview_save_persists_to_history_and_returns_location(client):
    with patch("src.seller_console.views._collect_real_draft", side_effect=lambda url, **k: _fake_draft(url=url)), \
         patch("src.seller_console.collect_history_store.append", return_value="hist42") as mock_append:
        resp = client.post("/seller/collect/preview", json={
            "url": "https://brand.example/product/1", "save": True})
    data = resp.get_json()
    assert data["ok"] is True
    assert data["id"] == "hist42"
    assert data["preview_url"] == "/seller/collect/preview/hist42"
    assert data["history_url"] == "/seller/collect/history"
    assert mock_append.call_count == 1


def test_preview_without_save_does_not_persist(client):
    with patch("src.seller_console.views._collect_real_draft", side_effect=lambda url, **k: _fake_draft(url=url)), \
         patch("src.seller_console.collect_history_store.append", return_value="x") as mock_append:
        resp = client.post("/seller/collect/preview", json={
            "url": "https://brand.example/product/1"})
    data = resp.get_json()
    assert data["ok"] is True
    assert "id" not in data
    assert mock_append.call_count == 0
