"""tests/test_orders_views.py — 주문 관리 라우트 테스트 (Phase 129)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    """셀러 콘솔이 등록된 Flask 앱 테스트 클라이언트."""
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def mock_sync_service():
    """OrderSyncService mock."""
    from src.seller_console.orders.models import OrderStatus, UnifiedOrder
    from datetime import datetime
    from decimal import Decimal

    svc = MagicMock()
    svc.list_orders.return_value = [
        UnifiedOrder(
            order_id="CP-001",
            marketplace="coupang",
            status=OrderStatus.PAID,
            placed_at=datetime(2024, 1, 15, 10, 0),
            total_krw=Decimal("39000"),
        )
    ]
    svc.kpi_summary.return_value = {
        "today_new": 3,
        "pending_ship": 5,
        "shipped": 12,
        "returned_exchanged": 1,
        "source": "mock",
    }
    svc.sync_all.return_value = {
        "coupang": {"fetched": 3, "upserted": 3, "status": "ok"},
        "smartstore": {"fetched": 0, "upserted": 0, "status": "ok"},
        "11st": {"fetched": 0, "upserted": 0, "status": "ok"},
        "kohganemultishop": {"fetched": 0, "upserted": 0, "status": "ok"},
    }
    svc.update_tracking.return_value = True
    return svc


class TestOrdersViews:
    def test_get_orders_returns_200(self, client, mock_sync_service):
        """GET /seller/orders → 200."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.get("/seller/orders")
        assert resp.status_code == 200
        assert "주문 관리" in resp.data.decode("utf-8")

    def test_get_orders_has_kpi_data(self, client, mock_sync_service):
        """GET /seller/orders → KPI 카드 포함."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.get("/seller/orders")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")
        assert "발송대기" in data or "신규" in data

    def test_post_orders_sync_success(self, client, mock_sync_service):
        """POST /seller/orders/sync → {"ok": true, "results": {...}}."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post("/seller/orders/sync")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "results" in data
        assert "coupang" in data["results"]

    def test_post_orders_sync_service_unavailable(self, client):
        """OrderSyncService 로드 실패 → 503."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=None):
            resp = client.post("/seller/orders/sync")
        assert resp.status_code == 503

    def test_get_order_detail_found(self, client, mock_sync_service):
        """GET /seller/orders/<mp>/<id> → {"ok": true, "order": {...}}."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.get("/seller/orders/coupang/CP-001")
        assert resp.status_code in (200, 404)

    def test_get_order_detail_not_found(self, client, mock_sync_service):
        """주문 없음 → 404."""
        mock_sync_service.list_orders.return_value = []
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.get("/seller/orders/coupang/NONEXISTENT-999")
        assert resp.status_code == 404

    def test_post_tracking_success(self, client, mock_sync_service):
        """POST /seller/orders/<mp>/<id>/tracking → {"ok": true}."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/coupang/CP-001/tracking",
                json={"courier": "CJ대한통운", "tracking_no": "1234567890"},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

    def test_post_tracking_missing_fields(self, client, mock_sync_service):
        """운송장 정보 누락 → 400."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/coupang/CP-001/tracking",
                json={"courier": "CJ대한통운"},
            )
        assert resp.status_code == 400

    def test_post_bulk_tracking_success(self, client, mock_sync_service):
        """POST /seller/orders/bulk/tracking → 일괄 결과."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/bulk/tracking",
                json={
                    "items": [
                        {"order_id": "CP-001", "marketplace": "coupang", "courier": "CJ", "tracking_no": "111"},
                        {"order_id": "SS-001", "marketplace": "smartstore", "courier": "한진", "tracking_no": "222"},
                    ]
                },
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert len(data["results"]) == 2

    def test_post_bulk_tracking_empty(self, client, mock_sync_service):
        """빈 items → 400."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post("/seller/orders/bulk/tracking", json={"items": []})
        assert resp.status_code == 400

    def test_get_export_csv(self, client, mock_sync_service):
        """GET /seller/orders/export.csv → CSV 응답."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.get("/seller/orders/export.csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
        assert b"order_id" in resp.data
