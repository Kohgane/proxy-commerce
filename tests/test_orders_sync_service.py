"""tests/test_orders_sync_service.py — OrderSyncService 테스트."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.seller_console.orders.models import OrderLineItem, OrderStatus, UnifiedOrder


def _make_order(order_id: str = "TEST-001", marketplace: str = "coupang") -> UnifiedOrder:
    return UnifiedOrder(
        order_id=order_id,
        marketplace=marketplace,
        status=OrderStatus.PAID,
        placed_at=datetime(2024, 1, 15, 10, 0, 0),
        total_krw=Decimal("39000"),
        items=[OrderLineItem(sku="SKU-A", title="상품 A", qty=1, unit_price_krw=Decimal("36000"))],
    )


class TestOrderSyncServiceSyncAll:
    def test_sync_all_success(self, monkeypatch):
        """sync_all: 모든 어댑터 정상 동작."""
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_ID", raising=False)
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)

        from src.seller_console.orders.sync_service import OrderSyncService

        svc = OrderSyncService()
        # Sheets adapter mock
        svc.sheets.bulk_upsert = MagicMock(return_value=0)

        results = svc.sync_all()
        assert isinstance(results, dict)
        assert "coupang" in results
        # 쿠팡은 API 키 없으므로 mock 3건 반환 → ok
        assert results["coupang"]["status"] == "ok"
        assert results["coupang"]["fetched"] == 3

    def test_sync_all_partial_failure(self, monkeypatch):
        """sync_all: 한 마켓 실패해도 다른 마켓은 계속."""
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)

        from src.seller_console.orders.sync_service import OrderSyncService

        svc = OrderSyncService()
        svc.sheets.bulk_upsert = MagicMock(return_value=0)

        # smartstore 어댑터가 예외 발생하도록 mock
        svc.adapters["smartstore"].fetch_orders_unified = MagicMock(side_effect=RuntimeError("네트워크 오류"))

        results = svc.sync_all()
        assert results["smartstore"]["status"] == "fail"
        assert "error" in results["smartstore"]
        # 쿠팡은 여전히 동작
        assert results["coupang"]["status"] == "ok"

    def test_sync_one_unknown_marketplace(self, monkeypatch):
        """sync_one: 알 수 없는 마켓 → fail."""
        from src.seller_console.orders.sync_service import OrderSyncService
        svc = OrderSyncService()
        result = svc.sync_one("unknown_market")
        assert result["status"] == "fail"


class TestOrderSyncServiceListOrders:
    def test_list_orders_no_sheets(self, monkeypatch):
        """GOOGLE_SHEET_ID 미설정 → 빈 목록."""
        monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)

        from src.seller_console.orders.sync_service import OrderSyncService
        svc = OrderSyncService()
        result = svc.list_orders()
        assert result == []

    def test_list_orders_with_mock_sheets(self, monkeypatch):
        """Sheets mock → 주문 목록 반환."""
        from src.seller_console.orders.sync_service import OrderSyncService

        svc = OrderSyncService()
        mock_orders = [_make_order("A-001"), _make_order("A-002")]
        svc.sheets.query = MagicMock(return_value=mock_orders)

        result = svc.list_orders(filters={"marketplace": "coupang"}, limit=10)
        assert len(result) == 2
        svc.sheets.query.assert_called_once()


class TestOrderSyncServiceKpiSummary:
    def test_kpi_summary_no_sheets(self, monkeypatch):
        """GOOGLE_SHEET_ID 미설정 → mock KPI 반환."""
        monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)

        from src.seller_console.orders.sync_service import OrderSyncService
        svc = OrderSyncService()
        kpi = svc.kpi_summary()
        assert "today_new" in kpi
        assert "pending_ship" in kpi
        assert "shipped" in kpi
        assert "returned_exchanged" in kpi

    def test_kpi_summary_with_mock(self):
        """Sheets mock → KPI 집계 반환."""
        from src.seller_console.orders.sync_service import OrderSyncService

        svc = OrderSyncService()
        mock_kpi = {
            "today_new": 5,
            "pending_ship": 10,
            "shipped": 20,
            "returned_exchanged": 2,
            "source": "sheets",
        }
        svc.sheets.kpi_summary = MagicMock(return_value=mock_kpi)

        kpi = svc.kpi_summary()
        assert kpi["today_new"] == 5
        assert kpi["shipped"] == 20

    def test_kpi_summary_exception_graceful(self):
        """kpi_summary 예외 발생 → graceful 폴백."""
        from src.seller_console.orders.sync_service import OrderSyncService

        svc = OrderSyncService()
        svc.sheets.kpi_summary = MagicMock(side_effect=RuntimeError("DB 오류"))

        kpi = svc.kpi_summary()
        assert kpi["source"] == "error"
        assert kpi["today_new"] == 0


class TestOrderSyncServiceUpdateTracking:
    def test_update_tracking_dry_run(self, monkeypatch):
        """ADAPTER_DRY_RUN=1 → 전송 없이 ok (API/Sheets 미호출).

        ※ F45: 반환이 bool → dict이다. 막은 것을 「성공」이라 부르되 **왜인지** 적는다.
        """
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")

        from src.seller_console.orders.sync_service import OrderSyncService
        svc = OrderSyncService()
        svc.sheets.update_tracking = MagicMock(return_value=True)

        result = svc.update_tracking("ORDER-001", "coupang", "CJ", "123456")
        assert result["ok"] is True
        assert "전송하지 않았습니다" in result["error"]
        # dry-run 이므로 Sheets 호출 안 함
        svc.sheets.update_tracking.assert_not_called()
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_update_tracking_sheets_only(self, monkeypatch):
        """★★★ API 키 없음 → 대장만 갱신되고, **그건 성공이 아니다** (F45).

        이 테스트는 예전에 `assert result is True`였다 — **쿠팡에 아무것도 안 갔는데
        성공이라고 못박고 있었다.** 계약이 거짓을 지키고 있었던 셈이다.
        지금은 두 사실이 다른 칸으로 나온다: 마켓 미반영(ok=False) · 우리 기록됨(local_ok=True).
        """
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)

        from src.seller_console.orders.sync_service import OrderSyncService
        svc = OrderSyncService()
        svc.sheets.update_tracking = MagicMock(return_value=True)

        result = svc.update_tracking("ORDER-001", "coupang", "CJGLS", "1234567890")
        assert result["ok"] is False
        assert result["local_ok"] is True
        assert result["error"]
        svc.sheets.update_tracking.assert_called_once_with("ORDER-001", "coupang", "CJGLS", "1234567890")
