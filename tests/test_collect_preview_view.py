"""tests/test_collect_preview_view.py — 수집 미리보기 페이지 테스트 (Phase 135.2).

GET /seller/collect/preview/<item_id> — 존재 ID → 200, 미존재 → 404.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
os.environ.setdefault("GOOGLE_SHEET_ID", "")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_MOCK_ITEM = {
    "id": "abc123",
    "collected_at": "2026-05-06T10:00:00+00:00",
    "source": "extension",
    "domain": "aloyoga.com",
    "url": "https://www.aloyoga.com/products/legging",
    "title": "Alo Legging",
    "image_url": "https://cdn.aloyoga.com/legging.jpg",
    "price": "98.00",
    "currency": "USD",
    "status": "ok",
    "preview_url": "/seller/collect/preview/abc123",
    "extra_json": '{"description": "test desc"}',
}


@pytest.fixture
def app():
    from src.order_webhook import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestCollectPreviewView:
    def test_preview_existing_id_200(self, client):
        """존재하는 ID → 200 OK."""
        with patch("src.seller_console.collect_history_store.get", return_value=_MOCK_ITEM):
            resp = client.get("/seller/collect/preview/abc123")
        assert resp.status_code == 200

    def test_preview_shows_title(self, client):
        """상품 제목이 미리보기 페이지에 표시됨."""
        with patch("src.seller_console.collect_history_store.get", return_value=_MOCK_ITEM):
            resp = client.get("/seller/collect/preview/abc123")
        assert b"Alo Legging" in resp.data

    def test_preview_nonexistent_id_404(self, client):
        """존재하지 않는 ID → 404."""
        with patch("src.seller_console.collect_history_store.get", return_value=None):
            resp = client.get("/seller/collect/preview/nonexistent999")
        assert resp.status_code == 404

    def test_preview_shows_price(self, client):
        """가격 정보가 표시됨."""
        with patch("src.seller_console.collect_history_store.get", return_value=_MOCK_ITEM):
            resp = client.get("/seller/collect/preview/abc123")
        assert b"98.00" in resp.data
        assert b"USD" in resp.data
