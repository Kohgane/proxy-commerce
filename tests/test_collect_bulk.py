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
    d = MagicMock()
    d.to_dict.return_value = {
        "title_ko": title, "title_en": title, "price_original": 19.9,
        "currency": "USD", "images": ["https://img/1.jpg"], "url": url,
    }
    return d


def test_bulk_empty_returns_400(client):
    resp = client.post("/seller/collect/bulk", json={"urls": ""})
    assert resp.status_code == 400


def test_bulk_collects_and_saves_to_history(client):
    svc = MagicMock()
    svc.extract.side_effect = lambda url: _fake_draft(url=url)
    with patch("src.seller_console.views._get_collector_service", return_value=svc), \
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
    svc = MagicMock()
    svc.extract.side_effect = lambda url: _fake_draft(url=url)
    with patch("src.seller_console.views._get_collector_service", return_value=svc), \
         patch("src.seller_console.collect_history_store.append", return_value="x"):
        resp = client.post("/seller/collect/bulk", json={
            "urls": "ftp://bad\nhttps://ok.com/a\nhttps://ok.com/a"})  # 비http + 중복
    data = resp.get_json()
    # 중복 제거 → 2개(ftp, ok), ftp는 실패
    assert data["total"] == 2
    by_ok = {r["ok"] for r in data["results"]}
    assert False in by_ok and True in by_ok


def test_bulk_per_url_error_isolated(client):
    svc = MagicMock()

    def _extract(url):
        if "bad" in url:
            raise RuntimeError("extract fail")
        return _fake_draft(url=url)
    svc.extract.side_effect = _extract
    with patch("src.seller_console.views._get_collector_service", return_value=svc), \
         patch("src.seller_console.collect_history_store.append", return_value="x"):
        resp = client.post("/seller/collect/bulk", json={
            "urls": "https://good.com/1\nhttps://bad.com/2"})
    data = resp.get_json()
    assert data["success"] == 1
    assert data["total"] == 2
