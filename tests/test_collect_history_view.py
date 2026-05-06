"""tests/test_collect_history_view.py — 수집 이력 페이지 테스트 (Phase 135.2).

GET /seller/collect/history 라우트 + 필터 동작 + 빈 목록 메시지 검증.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
os.environ.setdefault("GOOGLE_SHEET_ID", "")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_MOCK_ITEMS = [
    {
        "id": "abc123",
        "collected_at": "2026-05-06T10:00:00+00:00",
        "source": "extension",
        "domain": "aloyoga.com",
        "url": "https://www.aloyoga.com/products/legging",
        "title": "Alo Legging",
        "image_url": "",
        "price": "98.00",
        "currency": "USD",
        "status": "ok",
        "preview_url": "/seller/collect/preview/abc123",
        "extra_json": "{}",
    }
]
_MOCK_SUMMARY = {
    "total": 1,
    "today": 1,
    "domains": 1,
    "by_source": {"extension": 1, "bookmarklet": 0, "manual": 0, "bulk": 0},
}
_MOCK_DOMAINS = ["aloyoga.com"]


@pytest.fixture
def app():
    from src.order_webhook import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestCollectHistoryView:
    def test_history_page_200(self, client):
        """GET /seller/collect/history → 200."""
        with patch("src.seller_console.collect_history_store.list_items", return_value=_MOCK_ITEMS), \
             patch("src.seller_console.collect_history_store.summary", return_value=_MOCK_SUMMARY), \
             patch("src.seller_console.collect_history_store.distinct_domains", return_value=_MOCK_DOMAINS):
            resp = client.get("/seller/collect/history")
        assert resp.status_code == 200

    def test_history_page_shows_item_title(self, client):
        """수집된 상품 제목이 표시됨."""
        with patch("src.seller_console.collect_history_store.list_items", return_value=_MOCK_ITEMS), \
             patch("src.seller_console.collect_history_store.summary", return_value=_MOCK_SUMMARY), \
             patch("src.seller_console.collect_history_store.distinct_domains", return_value=_MOCK_DOMAINS):
            resp = client.get("/seller/collect/history")
        assert b"Alo Legging" in resp.data

    def test_history_empty_message(self, client):
        """수집 이력 없을 때 안내 메시지 표시."""
        empty_summary = {
            "total": 0, "today": 0, "domains": 0,
            "by_source": {"extension": 0, "bookmarklet": 0, "manual": 0, "bulk": 0},
        }
        with patch("src.seller_console.collect_history_store.list_items", return_value=[]), \
             patch("src.seller_console.collect_history_store.summary", return_value=empty_summary), \
             patch("src.seller_console.collect_history_store.distinct_domains", return_value=[]):
            resp = client.get("/seller/collect/history")
        assert resp.status_code == 200
        assert "수집 이력이 없습니다" in resp.data.decode("utf-8")

    def test_history_filter_by_domain(self, client):
        """도메인 필터 적용 시 URL 파라미터 반영."""
        with patch("src.seller_console.collect_history_store.list_items", return_value=_MOCK_ITEMS) as mock_list, \
             patch("src.seller_console.collect_history_store.summary", return_value=_MOCK_SUMMARY), \
             patch("src.seller_console.collect_history_store.distinct_domains", return_value=_MOCK_DOMAINS):
            resp = client.get("/seller/collect/history?domain=aloyoga.com")
        assert resp.status_code == 200
        # list_items 호출 시 domain 파라미터 전달 확인
        call_kwargs = mock_list.call_args[1] if mock_list.call_args else {}
        assert call_kwargs.get("domain") == "aloyoga.com"

    def test_history_filter_by_source(self, client):
        """source 필터 적용 시 list_items에 전달됨."""
        with patch("src.seller_console.collect_history_store.list_items", return_value=_MOCK_ITEMS) as mock_list, \
             patch("src.seller_console.collect_history_store.summary", return_value=_MOCK_SUMMARY), \
             patch("src.seller_console.collect_history_store.distinct_domains", return_value=_MOCK_DOMAINS):
            resp = client.get("/seller/collect/history?source=extension")
        assert resp.status_code == 200
        call_kwargs = mock_list.call_args[1] if mock_list.call_args else {}
        assert call_kwargs.get("source") == "extension"
