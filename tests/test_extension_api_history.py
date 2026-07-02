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
    @pytest.fixture(autouse=True)
    def _clean_store(self):
        # v42 1-3: 중복 수집 방지가 실 _in_memory를 읽으므로, append를 목킹하는 이 클래스 테스트는
        #   다른 파일이 남긴 같은 URL 행에 dedup되지 않도록 저장소를 비운다(테스트 격리).
        from src.seller_console import collect_history_store as ch
        ch._in_memory.clear()
        yield
        ch._in_memory.clear()

    def test_collect_records_history(self, client):
        """POST /api/v1/collect/extension → collect_history_store.append 호출됨."""
        with patch("src.api.extension_api._require_token") as mock_auth, \
             patch("src.api.extension_api._upsert_catalog") as mock_catalog, \
             patch("src.seller_console.collect_history_store.append") as mock_history, \
             patch("src.seller_console.collect_history_store.get", return_value={"id": "hist456"}), \
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
             patch("src.seller_console.collect_history_store.get", return_value={"id": "histxyz"}), \
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

    def test_collect_translates_and_stores_korean(self, client):
        """수집 시 번역 → extra에 title_ko/description_ko 저장 (Phase 202)."""
        fake_tr = {
            "title_ko": "알로 레깅스",
            "description_ko": "하이웨이스트 레깅스.",
            "provider": "openai",
        }
        with patch("src.api.extension_api._require_token") as mock_auth, \
             patch("src.api.extension_api._upsert_catalog", return_value="p1"), \
             patch("src.seller_console.collect_history_store.append", return_value="h1") as mock_history, \
             patch("src.seller_console.collect_history_store.get", return_value={"id": "h1"}), \
             patch("src.seller_console.ai.translator.AITranslator.translate_product", return_value=fake_tr), \
             patch("src.api.extension_api._notify_telegram"):
            mock_auth.return_value = {"user_id": "u1", "scopes": ["collect.write"]}
            resp = client.post(
                "/api/v1/collect/extension",
                data=json.dumps({
                    "url": "https://aloyoga.com/products/legging",
                    "title": "Alo Legging",
                    "description": "High-waist legging.",
                    "image": "https://aloyoga.com/l.jpg",
                    "price": "98.00", "currency": "USD",
                }),
                content_type="application/json",
                headers={"Authorization": "Bearer kgp_test"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["title_ko"] == "알로 레깅스"
        assert data["translated"] is True

        call_kwargs = mock_history.call_args[1]
        # 이력 상위 title은 한국어
        assert call_kwargs["title"] == "알로 레깅스"
        extra = call_kwargs["extra"]
        assert extra["title_ko"] == "알로 레깅스"
        assert extra["title_en"] == "Alo Legging"
        assert extra["description_ko"] == "하이웨이스트 레깅스."
        assert extra["images"] == ["https://aloyoga.com/l.jpg"]
        assert extra["translation_provider"] == "openai"

    def test_collect_translate_disabled_keeps_original(self, client):
        """translate=false면 번역 호출 없이 원문 유지."""
        with patch("src.api.extension_api._require_token") as mock_auth, \
             patch("src.api.extension_api._upsert_catalog", return_value="p1"), \
             patch("src.seller_console.collect_history_store.append", return_value="h1") as mock_history, \
             patch("src.seller_console.collect_history_store.get", return_value={"id": "h1"}), \
             patch("src.seller_console.ai.translator.AITranslator.translate_product") as mock_tr, \
             patch("src.api.extension_api._notify_telegram"):
            mock_auth.return_value = {"user_id": "u1", "scopes": ["collect.write"]}
            resp = client.post(
                "/api/v1/collect/extension",
                data=json.dumps({
                    "url": "https://shop.example.com/p",
                    "title": "Original Title", "translate": False,
                }),
                content_type="application/json",
                headers={"Authorization": "Bearer kgp_test"},
            )

        assert resp.status_code == 200
        mock_tr.assert_not_called()
        call_kwargs = mock_history.call_args[1]
        assert call_kwargs["title"] == "Original Title"

    def test_collect_history_failure_returns_honest_error(self, client):
        """history append 실패 시 가짜 성공 금지 — 정직한 실패(502 ok=false) 반환 (v4 P0)."""
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

        assert resp.status_code == 502
        data = resp.get_json()
        assert data["ok"] is False
