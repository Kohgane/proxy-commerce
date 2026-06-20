"""tests/test_extension_api.py — 크롬 확장 API 테스트 (Phase 135).

토큰 인증 + collect POST 검증.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
os.environ.setdefault("GOOGLE_SHEET_ID", "")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def app():
    from src.order_webhook import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestExtensionCollectAPI:
    def test_collect_no_token_401(self, client):
        resp = client.post(
            "/api/v1/collect/extension",
            data=json.dumps({"url": "https://example.com/p", "title": "T"}),
            content_type="application/json",
        )
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["ok"] is False

    def test_collect_with_token_200(self, client):
        """유효한 토큰으로 수집 성공."""
        with patch("src.api.extension_api._require_token") as mock_auth:
            mock_auth.return_value = {"user_id": "test_user", "scopes": ["collect.write"]}
            with patch("src.api.extension_api._upsert_catalog") as mock_upsert:
                mock_upsert.return_value = "abc123"
                with patch("src.api.extension_api._notify_telegram"):
                    resp = client.post(
                        "/api/v1/collect/extension",
                        data=json.dumps({
                            "url": "https://aloyoga.com/products/legging",
                            "title": "Alo Legging",
                            "price": "98.00",
                            "currency": "USD",
                        }),
                        content_type="application/json",
                        headers={"Authorization": "Bearer tok_test"},
                    )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "preview_url" in data
        assert data["product_id"] == "abc123"

    def test_collect_html_server_parse_enriches_price(self, client):
        """봇 차단 사이트: 확장이 보낸 HTML을 서버가 파싱해 가격 0 → 실가격 보강 (Phase 212)."""
        jsonld_html = (
            '<html><head><script type="application/ld+json">'
            '{"@type":"Product","name":"Porter Backpack",'
            '"image":["https://img.y.com/bag.jpg"],'
            '"offers":{"price":"33000","priceCurrency":"JPY"}}'
            '</script></head></html>'
        )
        captured = {}

        def _fake_append(**kwargs):
            captured.update(kwargs)
            return "hist1"

        with patch("src.api.extension_api._require_token") as mock_auth:
            mock_auth.return_value = {"user_id": "u1", "scopes": ["collect.write"]}
            with patch("src.api.extension_api._upsert_catalog", return_value="cat1"), \
                 patch("src.api.extension_api._notify_telegram"), \
                 patch("src.seller_console.collect_history_store.append", _fake_append), \
                 patch("src.seller_console.collect_history_store.get", return_value={"id": "hist1"}):
                resp = client.post(
                    "/api/v1/collect/extension",
                    data=json.dumps({
                        "url": "https://www.yoshidakaban.com/ko/product/102492.html",
                        "title": "",
                        "price": "0",
                        "currency": "USD",
                        "translate": False,
                        "html": jsonld_html,
                    }),
                    content_type="application/json",
                    headers={"Authorization": "Bearer tok_test"},
                )
        assert resp.status_code == 200
        # 서버 파싱으로 가격/통화/제목/이미지가 보강됨
        assert str(captured.get("price")) == "33000"
        assert captured.get("currency") == "JPY"
        extra = captured.get("extra") or {}
        assert extra.get("price_original") == "33000"
        assert "https://img.y.com/bag.jpg" in (extra.get("images") or [])
        # 대용량 html은 이력 extra에 저장하지 않음
        assert "html" not in extra

    def test_collect_no_url_400(self, client):
        with patch("src.api.extension_api._require_token") as mock_auth:
            mock_auth.return_value = {"user_id": "test_user", "scopes": ["collect.write"]}
            resp = client.post(
                "/api/v1/collect/extension",
                data=json.dumps({"title": "No URL"}),
                content_type="application/json",
                headers={"Authorization": "Bearer tok_test"},
            )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False


class TestBulkCollectAPI:
    def test_bulk_no_token_401(self, client):
        resp = client.post(
            "/api/v1/collect/bulk",
            data=json.dumps({"urls": ["https://example.com"]}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_bulk_start_success(self, client):
        with patch("src.api.extension_api._require_token") as mock_auth:
            mock_auth.return_value = {"user_id": "test_user", "scopes": ["collect.write"]}
            resp = client.post(
                "/api/v1/collect/bulk",
                data=json.dumps({
                    "urls": [
                        "https://aloyoga.com/products/p1",
                        "https://aloyoga.com/products/p2",
                    ]
                }),
                content_type="application/json",
                headers={"Authorization": "Bearer tok_test"},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "job_id" in data
        assert data["total"] == 2
        assert data["status"] == "running"

    def test_bulk_empty_urls_400(self, client):
        with patch("src.api.extension_api._require_token") as mock_auth:
            mock_auth.return_value = {"user_id": "test_user", "scopes": ["collect.write"]}
            resp = client.post(
                "/api/v1/collect/bulk",
                data=json.dumps({"urls": []}),
                content_type="application/json",
                headers={"Authorization": "Bearer tok_test"},
            )
        assert resp.status_code == 400

    def test_bulk_poll_not_found(self, client):
        with patch("src.api.extension_api._require_token") as mock_auth:
            mock_auth.return_value = {"user_id": "test_user", "scopes": ["collect.write"]}
            resp = client.get(
                "/api/v1/collect/bulk/nonexistent-job-id",
                headers={"Authorization": "Bearer tok_test"},
            )
        assert resp.status_code == 404


class TestCronDiscovery:
    def test_cron_discovery_dry_run(self, client):
        """DRY_RUN=1에서 discovery cron 즉시 skip."""
        resp = client.post("/cron/discovery")
        data = resp.get_json()
        assert data["ok"] is True
        assert data["status"] == "dry_run"
