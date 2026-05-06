"""tests/test_extension_api_history.py — extension API 수집 이력 기록 테스트 (Phase 135.2).

POST /api/v1/collect/extension → history append 됨 + preview_url 형식 검증.
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


class TestExtensionApiHistory:
    def test_collect_records_history(self, client):
        """POST /api/v1/collect/extension → collect_history_store.append 호출됨."""
        with patch("src.api.extension_api._require_token") as mock_auth, \
             patch("src.api.extension_api._upsert_catalog") as mock_catalog, \
             patch("src.seller_console.collect_history_store.append") as mock_history, \
             patch("src.api.extension_api._notify_telegram"):
            mock_auth.return_value = {"user_id": "test_user", "scopes": ["collect.write"]}
            mock_catalog.return_value = "prod123"
            mock_history.return_value = "hist456"

            resp = client.post(
                "/api/v1/collect/extension",
                data=json.dumps({
                    "url": "https://aloyoga.com/products/legging",
                    "title": "Alo Legging",
                    "price": "98.00",
                    "currency": "USD",
                }),
                content_type="application/json",
                headers={"Authorization": "Bearer kgp_test"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        # history append가 호출되었는지 확인
        mock_history.assert_called_once()
        call_kwargs = mock_history.call_args[1]
        assert call_kwargs["source"] == "extension"
        assert call_kwargs["url"] == "https://aloyoga.com/products/legging"
        assert call_kwargs["title"] == "Alo Legging"

    def test_collect_preview_url_format(self, client):
        """preview_url이 /seller/collect/preview/<item_id> 형식임."""
        with patch("src.api.extension_api._require_token") as mock_auth, \
             patch("src.api.extension_api._upsert_catalog") as mock_catalog, \
             patch("src.seller_console.collect_history_store.append") as mock_history, \
             patch("src.api.extension_api._notify_telegram"):
            mock_auth.return_value = {"user_id": "test_user", "scopes": ["collect.write"]}
            mock_catalog.return_value = "prod123"
            mock_history.return_value = "histxyz"

            resp = client.post(
                "/api/v1/collect/extension",
                data=json.dumps({
                    "url": "https://aloyoga.com/products/legging",
                    "title": "Alo Legging",
                }),
                content_type="application/json",
                headers={"Authorization": "Bearer kgp_test"},
            )

        data = resp.get_json()
        assert data["ok"] is True
        assert data["preview_url"] == "/seller/collect/preview/histxyz"

    def test_collect_history_failure_does_not_break_response(self, client):
        """history append 실패해도 수집 응답은 정상."""
        with patch("src.api.extension_api._require_token") as mock_auth, \
             patch("src.api.extension_api._upsert_catalog") as mock_catalog, \
             patch("src.seller_console.collect_history_store.append",
                   side_effect=Exception("Sheets 연결 실패")), \
             patch("src.api.extension_api._notify_telegram"):
            mock_auth.return_value = {"user_id": "test_user", "scopes": ["collect.write"]}
            mock_catalog.return_value = "prod123"

            resp = client.post(
                "/api/v1/collect/extension",
                data=json.dumps({
                    "url": "https://aloyoga.com/products/legging",
                    "title": "Alo Legging",
                }),
                content_type="application/json",
                headers={"Authorization": "Bearer kgp_test"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
