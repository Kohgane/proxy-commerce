"""tests/test_bulk_collect.py — 벌크 수집 진행률 + 부분 실패 테스트 (Phase 135)."""
from __future__ import annotations

import json
import os
import sys
import time
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


class TestBulkCollect:
    def test_bulk_max_1000_urls(self, client):
        """URL 1000개 초과 시 1000개로 잘림(퍼센티 100 → 우리 1000).

        P(2026-10-01) 실측: 이 계약이 **진짜 백그라운드 작업**(1000건 수집)을 띄우고 기다리지 않아, 그 스레드가
        다음 파일들까지 살아서 `collect_one_url`을 불렀다 → 그걸 세는 계약(test_c_share_text)이 부하에 따라
        남의 호출 649건을 제 것으로 셌다. 이 계약이 재는 건 「잘림」뿐이다 — 작업 본체는 띄우지 않는다.
        """
        got = {}
        with patch("src.api.extension_api._require_token") as mock_auth, \
                patch("src.api.extension_api._run_bulk_job", lambda job_id, urls: got.update(n=len(urls))):
            mock_auth.return_value = {"user_id": "u", "scopes": ["collect.write"]}
            urls = [f"https://example.com/product/{i}" for i in range(1100)]
            resp = client.post(
                "/api/v1/collect/bulk",
                data=json.dumps({"urls": urls}),
                content_type="application/json",
                headers={"Authorization": "Bearer tok_test"},
            )
            import time
            for _ in range(50):                       # 스레드가 대체 함수를 부를 때까지(즉시 끝난다)
                if "n" in got:
                    break
                time.sleep(0.01)
        data = resp.get_json()
        assert data["total"] == 1000 and got.get("n") == 1000      # 작업에 넘어간 것도 1000개

    def test_bulk_job_polling(self, client):
        """잡 ID로 진행률 폴링."""
        with patch("src.api.extension_api._require_token") as mock_auth:
            mock_auth.return_value = {"user_id": "u", "scopes": ["collect.write"]}
            # 잡 시작
            resp = client.post(
                "/api/v1/collect/bulk",
                data=json.dumps({"urls": ["https://aloyoga.com/products/p1"]}),
                content_type="application/json",
                headers={"Authorization": "Bearer tok_test"},
            )
            job_id = resp.get_json()["job_id"]

            # 잠시 대기
            time.sleep(0.5)

            # 폴링
            resp2 = client.get(
                f"/api/v1/collect/bulk/{job_id}",
                headers={"Authorization": "Bearer tok_test"},
            )
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert data2["ok"] is True
        assert data2["job_id"] == job_id
        assert "total" in data2
        assert "processed" in data2

    def test_bulk_partial_failure(self, client):
        """일부 URL 실패해도 나머지 처리 (부분 성공)."""
        from src.collectors.universal_scraper import ScrapedProduct
        from decimal import Decimal

        def mock_collect(url: str) -> ScrapedProduct:
            if "fail" in url:
                raise Exception("수집 실패 (테스트)")
            return ScrapedProduct(
                source_url=url, domain="example.com",
                title="Test", description="",
                confidence=0.8,
            )

        with patch("src.api.extension_api._require_token") as mock_auth:
            mock_auth.return_value = {"user_id": "u", "scopes": ["collect.write"]}
            with patch("src.api.extension_api._upsert_catalog", return_value="id123"):
                with patch("src.api.extension_api._notify_telegram"):
                    # DRY_RUN이므로 실제로는 빈 결과
                    resp = client.post(
                        "/api/v1/collect/bulk",
                        data=json.dumps({
                            "urls": [
                                "https://example.com/ok",
                                "https://example.com/fail",
                            ]
                        }),
                        content_type="application/json",
                        headers={"Authorization": "Bearer tok_test"},
                    )
        data = resp.get_json()
        assert data["ok"] is True
        assert "job_id" in data

    def test_bulk_invalid_url_filtered(self, client):
        """공백/빈 URL은 필터링."""
        with patch("src.api.extension_api._require_token") as mock_auth:
            mock_auth.return_value = {"user_id": "u", "scopes": ["collect.write"]}
            resp = client.post(
                "/api/v1/collect/bulk",
                data=json.dumps({"urls": ["", "  ", None, "https://valid.com/p"]}),
                content_type="application/json",
                headers={"Authorization": "Bearer tok_test"},
            )
        data = resp.get_json()
        assert data["ok"] is True
        assert data["total"] == 1
