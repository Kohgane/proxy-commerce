"""tests/test_seller_market_views.py — 마켓 현황 API 라우트 테스트 (Phase 127).

GET  /seller/markets           → 200
GET  /seller/markets/status    → 200 + JSON 스키마
POST /seller/markets/sync      → 200 + JSON 결과
GET  /seller/market-status     → 302 (리다이렉트)
"""
from __future__ import annotations

import sys
import os
import json
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """셀러 콘솔이 등록된 Flask 앱 테스트 클라이언트."""
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# 헬퍼: MarketStatusService 목업
# ---------------------------------------------------------------------------

def _mock_service_get_all():
    """AllMarketStatus 목업을 반환하는 MarketStatusService 패치용 함수."""
    from src.seller_console.market_status import AllMarketStatus, MarketStatusSummary
    from datetime import datetime

    mock_result = AllMarketStatus(
        summaries=[
            MarketStatusSummary(marketplace="coupang", active=45, out_of_stock=3, error=1, total=49, source="sheets"),
            MarketStatusSummary(marketplace="smartstore", active=38, out_of_stock=5, error=0, total=43, source="sheets"),
        ],
        items=[],
        fetched_at=datetime(2026, 5, 3, 12, 0, 0),
        source="sheets",
    )
    mock_svc = MagicMock()
    mock_svc.get_all.return_value = mock_result
    mock_svc.live_adapters = {"coupang": MagicMock(), "smartstore": MagicMock()}
    mock_svc.sync_marketplace.return_value = 0
    return mock_svc


# ---------------------------------------------------------------------------
# 테스트: GET /seller/markets
# ---------------------------------------------------------------------------

class TestMarketsOverview:
    """GET /seller/markets 라우트 테스트."""

    def test_markets_returns_200(self, client):
        """GET /seller/markets → 200."""
        resp = client.get("/seller/markets")
        assert resp.status_code == 200

    def test_markets_contains_market_data(self, client):
        """GET /seller/markets → HTML에 마켓 정보 포함."""
        resp = client.get("/seller/markets")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")
        assert "마켓" in data or "상품" in data


# ---------------------------------------------------------------------------
# 테스트: GET /seller/market-status (리다이렉트)
# ---------------------------------------------------------------------------

class TestMarketStatusRedirect:
    """GET /seller/market-status → /seller/markets 리다이렉트."""

    def test_market_status_redirects(self, client):
        """GET /seller/market-status → 302 리다이렉트."""
        resp = client.get("/seller/market-status")
        assert resp.status_code in (301, 302)

    def test_market_status_redirects_to_markets(self, client):
        """GET /seller/market-status → /seller/markets 로 리다이렉트."""
        resp = client.get("/seller/market-status")
        location = resp.headers.get("Location", "")
        assert "markets" in location


# ---------------------------------------------------------------------------
# 테스트: GET /seller/markets/status
# ---------------------------------------------------------------------------

class TestMarketsStatusApi:
    """GET /seller/markets/status JSON API 테스트."""

    def test_status_returns_200(self, client):
        """GET /seller/markets/status → 200."""
        resp = client.get("/seller/markets/status")
        assert resp.status_code == 200

    def test_status_returns_json(self, client):
        """GET /seller/markets/status → JSON."""
        resp = client.get("/seller/markets/status")
        assert resp.content_type.startswith("application/json")

    def test_status_json_has_summaries(self, client):
        """GET /seller/markets/status → 'summaries' 키 존재."""
        resp = client.get("/seller/markets/status")
        data = resp.get_json()
        assert "summaries" in data
        assert isinstance(data["summaries"], list)

    def test_status_json_has_source(self, client):
        """GET /seller/markets/status → 'source' 키 존재."""
        resp = client.get("/seller/markets/status")
        data = resp.get_json()
        assert "source" in data

    def test_status_json_has_fetched_at(self, client):
        """GET /seller/markets/status → 'fetched_at' 키 존재."""
        resp = client.get("/seller/markets/status")
        data = resp.get_json()
        assert "fetched_at" in data

    def test_status_summary_has_required_fields(self, client):
        """summaries 항목에 필수 필드 존재."""
        resp = client.get("/seller/markets/status")
        data = resp.get_json()
        if data["summaries"]:
            summary = data["summaries"][0]
            for field in ["marketplace", "active", "out_of_stock", "error", "total"]:
                assert field in summary, f"summary에 '{field}' 필드 없음"


# ---------------------------------------------------------------------------
# 테스트: POST /seller/markets/sync
# ---------------------------------------------------------------------------

class TestMarketsSyncApi:
    """POST /seller/markets/sync 테스트."""

    def test_sync_all_returns_200(self, client):
        """POST /seller/markets/sync (all) → 200."""
        resp = client.post(
            "/seller/markets/sync",
            data=json.dumps({"marketplace": "all"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_sync_returns_json(self, client):
        """POST /seller/markets/sync → JSON."""
        resp = client.post(
            "/seller/markets/sync",
            data=json.dumps({"marketplace": "all"}),
            content_type="application/json",
        )
        assert resp.content_type.startswith("application/json")

    def test_sync_specific_market(self, client):
        """POST /seller/markets/sync (coupang) → 200."""
        resp = client.post(
            "/seller/markets/sync",
            data=json.dumps({"marketplace": "coupang"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "coupang" in data

    def test_sync_empty_body_defaults_to_all(self, client):
        """POST /seller/markets/sync (빈 body) → 200."""
        resp = client.post(
            "/seller/markets/sync",
            data=b"",
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_sync_result_values_are_integers(self, client):
        """sync 결과 값이 정수."""
        resp = client.post(
            "/seller/markets/sync",
            data=json.dumps({"marketplace": "all"}),
            content_type="application/json",
        )
        data = resp.get_json()
        for v in data.values():
            assert isinstance(v, int)


# ---------------------------------------------------------------------------
# 테스트: GET /seller/health (Phase 127로 업데이트)
# ---------------------------------------------------------------------------

class TestHealthPhase127:
    """GET /seller/health phase 번호 업데이트 테스트."""

    def test_health_phase_is_127(self, client):
        """GET /seller/health → phase >= 127."""
        resp = client.get("/seller/health")
        data = resp.get_json()
        assert data["phase"] >= 127
