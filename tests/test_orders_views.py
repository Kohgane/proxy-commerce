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
        data = resp.data.decode("utf-8")
        assert "주문 관리" in data
        assert 'id="tm-courier"' in data
        assert 'id="tm-courier-listbox"' in data
        assert 'id="tm-courier-catalog"' in data

    def test_get_orders_renders_bulk_action_ui_elements(self, client, mock_sync_service):
        """체크박스/일괄 액션/모달 UI가 렌더링된다."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.get("/seller/orders")
        html = resp.get_data(as_text=True)
        assert 'id="ordersSelectAll"' in html
        assert "order-row-chk" in html
        assert 'id="bulkTrackingButton"' in html
        assert 'id="bulkStatusModal"' in html
        assert 'id="statusModal"' in html

    def test_get_orders_removes_prompt_based_status_change(self, client, mock_sync_service):
        """주문 페이지에 window.prompt 기반 상태 변경이 남아 있지 않다."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.get("/seller/orders")
        html = resp.get_data(as_text=True)
        assert "prompt(" not in html

    def test_get_orders_has_kpi_data(self, client, mock_sync_service):
        """GET /seller/orders → KPI 카드 포함."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.get("/seller/orders")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")
        assert "발송대기" in data or "신규" in data

    def test_get_orders_shows_service_unavailable_diagnostics_hint(self, client):
        """서비스 미가용이면 운영 진단 안내를 노출한다."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=None):
            resp = client.get("/seller/orders")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "주문 서비스가 일시적으로 준비되지 않았습니다(503)." in html
        assert "/admin/diagnostics" in html

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
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["order"]["order_id"] == "CP-001"

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

    def test_post_tracking_allows_free_text_courier(self, client, mock_sync_service):
        """목록에 없는 택배사 입력도 저장 경로를 막지 않는다."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/coupang/CP-001/tracking",
                json={"courier": "신규택배", "tracking_no": "1234567890"},
            )
        assert resp.status_code == 200
        mock_sync_service.update_tracking.assert_called_with("CP-001", "coupang", "신규택배", "1234567890")

    def test_post_tracking_missing_fields(self, client, mock_sync_service):
        """운송장 정보 누락 → 400."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/coupang/CP-001/tracking",
                json={"courier": "CJ대한통운"},
            )
        assert resp.status_code == 400

    def test_post_order_status_success(self, client, mock_sync_service):
        """POST /seller/orders/<mp>/<id>/status → 상태 변경 성공."""
        from src.seller_console.orders.models import OrderStatus, UnifiedOrder
        from datetime import datetime
        from decimal import Decimal

        mock_sync_service.list_orders.return_value = [
            UnifiedOrder(
                order_id="CP-001",
                marketplace="coupang",
                status=OrderStatus.PREPARING,
                placed_at=datetime(2024, 1, 15, 10, 0),
                total_krw=Decimal("39000"),
            )
        ]
        mock_sync_service.update_status.return_value = {"ok": True, "status": "shipped"}

        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/coupang/CP-001/status",
                json={"next_status": "shipped", "reason": "출고 완료"},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["status"] == "shipped"

    def test_post_order_status_invalid_transition(self, client, mock_sync_service):
        """허용되지 않은 상태 전이는 400으로 거절한다."""
        from src.seller_console.orders.models import OrderStatus, UnifiedOrder
        from datetime import datetime
        from decimal import Decimal

        mock_sync_service.list_orders.return_value = [
            UnifiedOrder(
                order_id="CP-001",
                marketplace="coupang",
                status=OrderStatus.NEW,
                placed_at=datetime(2024, 1, 15, 10, 0),
                total_krw=Decimal("39000"),
            )
        ]

        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/coupang/CP-001/status",
                json={"next_status": "shipped"},
            )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_post_order_status_service_unavailable(self, client):
        """서비스 미가용 시 503을 반환한다."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=None):
            resp = client.post(
                "/seller/orders/coupang/CP-001/status",
                json={"next_status": "shipped"},
            )
        assert resp.status_code == 503

    def test_post_order_status_internal_error(self, client, mock_sync_service):
        """상태 조회/변경 중 예외가 나면 500으로 복구한다."""
        mock_sync_service.list_orders.side_effect = RuntimeError("boom")

        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/coupang/CP-001/status",
                json={"next_status": "shipped"},
            )
        assert resp.status_code == 500
        data = resp.get_json()
        assert data["ok"] is False

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

    def test_post_bulk_tracking_partial_failure_on_empty_item(self, client, mock_sync_service):
        """빈 항목이 섞이면 부분 실패로 처리한다."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/bulk/tracking",
                json={
                    "items": [
                        {"order_id": "CP-001", "marketplace": "coupang", "courier": "CJ", "tracking_no": "111"},
                        {"order_id": "CP-002", "marketplace": "coupang", "courier": "CJ", "tracking_no": ""},
                    ]
                },
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False
        assert data["success_count"] == 1
        assert data["failed_count"] == 1
        assert any((not row["ok"]) for row in data["results"])
        mock_sync_service.update_tracking.assert_called_once_with("CP-001", "coupang", "CJ", "111")

    def test_post_bulk_tracking_empty(self, client, mock_sync_service):
        """빈 items → 400."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post("/seller/orders/bulk/tracking", json={"items": []})
        assert resp.status_code == 400

    def test_post_bulk_tracking_service_unavailable(self, client):
        """서비스 없음 → 503."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=None):
            resp = client.post(
                "/seller/orders/bulk/tracking",
                json={"items": [{"order_id": "CP-001", "marketplace": "coupang", "courier": "CJ", "tracking_no": "111"}]},
            )
        assert resp.status_code == 503

    def test_post_bulk_status_success(self, client, mock_sync_service):
        """POST /seller/orders/bulk/status → 선택 주문 상태가 일괄 변경된다."""
        from src.seller_console.orders.models import OrderStatus, UnifiedOrder
        from datetime import datetime
        from decimal import Decimal

        mock_sync_service.list_orders.side_effect = [
            [
                UnifiedOrder(
                    order_id="CP-001",
                    marketplace="coupang",
                    status=OrderStatus.PREPARING,
                    placed_at=datetime(2024, 1, 15, 10, 0),
                    total_krw=Decimal("39000"),
                )
            ],
            [
                UnifiedOrder(
                    order_id="CP-002",
                    marketplace="coupang",
                    status=OrderStatus.PREPARING,
                    placed_at=datetime(2024, 1, 15, 10, 5),
                    total_krw=Decimal("41000"),
                )
            ],
        ]
        mock_sync_service.update_status.return_value = {"ok": True, "status": "shipped", "adapter": {"applied": True, "simulated": False}}

        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/bulk/status",
                json={
                    "items": [
                        {"order_id": "CP-001", "marketplace": "coupang"},
                        {"order_id": "CP-002", "marketplace": "coupang"},
                    ],
                    "next_status": "shipped",
                    "reason": "일괄 출고",
                },
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["success_count"] == 2
        assert data["failed_count"] == 0
        assert mock_sync_service.update_status.call_count == 2

    def test_post_bulk_status_empty_selection(self, client, mock_sync_service):
        """선택 주문이 없으면 400."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post("/seller/orders/bulk/status", json={"items": [], "next_status": "shipped"})
        assert resp.status_code == 400

    def test_post_bulk_status_service_unavailable(self, client):
        """서비스 없음 → 503."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=None):
            resp = client.post(
                "/seller/orders/bulk/status",
                json={"items": [{"order_id": "CP-001", "marketplace": "coupang"}], "next_status": "shipped"},
            )
        assert resp.status_code == 503

    def test_post_bulk_status_rejects_invalid_transition(self, client, mock_sync_service):
        """공통 상태 전이가 불가능한 주문은 실패로 반환된다."""
        from src.seller_console.orders.models import OrderStatus, UnifiedOrder
        from datetime import datetime
        from decimal import Decimal

        mock_sync_service.list_orders.return_value = [
            UnifiedOrder(
                order_id="CP-001",
                marketplace="coupang",
                status=OrderStatus.NEW,
                placed_at=datetime(2024, 1, 15, 10, 0),
                total_krw=Decimal("39000"),
            )
        ]

        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.post(
                "/seller/orders/bulk/status",
                json={"items": [{"order_id": "CP-001", "marketplace": "coupang"}], "next_status": "shipped"},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False
        assert data["failed_count"] == 1

    def test_get_export_csv(self, client, mock_sync_service):
        """GET /seller/orders/export.csv → 기본 CSV 포맷을 반환한다."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=mock_sync_service):
            resp = client.get("/seller/orders/export.csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
        rows = resp.get_data(as_text=True).splitlines()
        header = rows[0].split(",")
        for field in [
            "order_id",
            "marketplace",
            "status",
            "placed_at",
            "buyer_name_masked",
            "total_krw",
            "items_count",
            "courier",
            "tracking_no",
            "notes",
        ]:
            assert field in header
        assert "CP-001,coupang,paid" in rows[1]

    def test_get_export_csv_service_unavailable(self, client):
        """서비스 미가용 시 CSV 대신 503 안내를 반환한다."""
        with patch("src.seller_console.views._get_order_sync_service", return_value=None):
            resp = client.get("/seller/orders/export.csv")
        assert resp.status_code == 503
        assert "잠시 후 다시 시도" in resp.get_data(as_text=True)
