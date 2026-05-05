"""tests/test_orders_sync_with_woo.py — OrderSyncService에 woocommerce 포함 테스트 (Phase 132).

- sync_all에 woocommerce 어댑터 포함
- kohganemultishop 어댑터 제거 확인
- WooCommerceAdapter.fetch_orders_unified mock 검증
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


MOCK_WOO_ORDERS = [
    {
        "id": 1001,
        "status": "processing",
        "date_created_gmt": "2026-05-01T10:00:00",
        "date_paid_gmt": "2026-05-01T10:05:00",
        "billing": {
            "first_name": "김",
            "last_name": "철수",
            "phone": "010-1234-5678",
            "city": "서울",
        },
        "total": "79000",
        "shipping_total": "3000",
        "line_items": [
            {
                "product_id": 101,
                "sku": "WC-001",
                "name": "테스트 상품",
                "quantity": 1,
                "price": "79000",
            }
        ],
    }
]


# ---------------------------------------------------------------------------
# 1. OrderSyncService 어댑터 구성
# ---------------------------------------------------------------------------

class TestOrderSyncServiceAdapters:
    def test_woocommerce_in_adapters(self):
        """OrderSyncService.adapters에 woocommerce 포함."""
        from src.seller_console.orders.sync_service import OrderSyncService

        mock_sheets = MagicMock()
        with patch("src.seller_console.orders.sync_service.OrderSyncService.__init__", return_value=None):
            svc = OrderSyncService.__new__(OrderSyncService)

        # 실제 __init__ 호출 (sheets mock 사용)
        with patch("src.seller_console.orders.sheets_adapter.OrderSheetsAdapter") as MockSheets:
            MockSheets.return_value = mock_sheets
            svc2 = OrderSyncService()

        assert "woocommerce" in svc2.adapters

    def test_kohganemultishop_not_in_adapters(self):
        """OrderSyncService.adapters에 kohganemultishop 제거됨."""
        with patch("src.seller_console.orders.sheets_adapter.OrderSheetsAdapter") as MockSheets:
            MockSheets.return_value = MagicMock()
            from src.seller_console.orders.sync_service import OrderSyncService
            svc = OrderSyncService()

        assert "kohganemultishop" not in svc.adapters

    def test_legacy_adapters_still_present(self):
        """coupang, smartstore, 11st 어댑터는 여전히 존재."""
        with patch("src.seller_console.orders.sheets_adapter.OrderSheetsAdapter") as MockSheets:
            MockSheets.return_value = MagicMock()
            from src.seller_console.orders.sync_service import OrderSyncService
            svc = OrderSyncService()

        for name in ("coupang", "smartstore", "11st"):
            assert name in svc.adapters, f"{name} not in adapters"


# ---------------------------------------------------------------------------
# 2. WooCommerceAdapter.fetch_orders_unified
# ---------------------------------------------------------------------------

class TestWooCommerceOrdersFetch:
    @pytest.fixture
    def mock_wc_env(self, monkeypatch):
        monkeypatch.setenv("WC_KEY", "ck_test")
        monkeypatch.setenv("WC_SECRET", "cs_test")
        monkeypatch.setenv("WC_URL", "https://kohganemultishop.org")
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_fetch_orders_unified_mock(self, mock_wc_env):
        """fetch_orders_unified HTTP mock 검증."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = [MOCK_WOO_ORDERS, []]  # page1 → page2 empty
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
            adapter = WooCommerceAdapter()
            orders = adapter.fetch_orders_unified()

        assert len(orders) == 1
        order = orders[0]
        assert order["order_id"] == "1001"
        assert order["marketplace"] == "woocommerce"
        assert order["status"] == "paid"  # processing → paid

    def test_fetch_orders_unified_no_keys(self, monkeypatch):
        """키 미설정 시 빈 리스트."""
        for k in ("WC_KEY", "WC_SECRET", "WC_URL", "WOO_CK", "WOO_CS", "WOO_BASE_URL"):
            monkeypatch.delenv(k, raising=False)
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        assert WooCommerceAdapter().fetch_orders_unified() == []

    def test_fetch_orders_dry_run(self, mock_wc_env, monkeypatch):
        """ADAPTER_DRY_RUN=1 시 빈 리스트."""
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        assert WooCommerceAdapter().fetch_orders_unified() == []

    def test_order_status_mapping(self, mock_wc_env):
        """WooCommerce 주문 상태 매핑 확인."""
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        adapter = WooCommerceAdapter()
        assert adapter._map_order_status("pending") == "new"
        assert adapter._map_order_status("processing") == "paid"
        assert adapter._map_order_status("completed") == "delivered"
        assert adapter._map_order_status("cancelled") == "canceled"
        assert adapter._map_order_status("refunded") == "returned"
        assert adapter._map_order_status("failed") == "canceled"
        assert adapter._map_order_status("unknown") == "new"

    def test_woo_order_to_unified_fields(self, mock_wc_env):
        """_woo_order_to_unified 변환 필드 확인."""
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        adapter = WooCommerceAdapter()
        unified = adapter._woo_order_to_unified(MOCK_WOO_ORDERS[0])
        assert unified["order_id"] == "1001"
        assert unified["marketplace"] == "woocommerce"
        assert unified["total_krw"] == "79000"
        assert len(unified["items"]) == 1
        assert unified["items"][0]["sku"] == "WC-001"


# ---------------------------------------------------------------------------
# 3. update_tracking
# ---------------------------------------------------------------------------

class TestWooCommerceUpdateTracking:
    @pytest.fixture
    def mock_wc_env(self, monkeypatch):
        monkeypatch.setenv("WC_KEY", "ck_test")
        monkeypatch.setenv("WC_SECRET", "cs_test")
        monkeypatch.setenv("WC_URL", "https://kohganemultishop.org")
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_update_tracking_success(self, mock_wc_env):
        """update_tracking 성공 시 True."""
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp):
            from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
            assert WooCommerceAdapter().update_tracking("1001", "CJ대한통운", "12345678") is True

    def test_update_tracking_no_keys(self, monkeypatch):
        """키 미설정 시 False."""
        for k in ("WC_KEY", "WC_SECRET", "WC_URL", "WOO_CK", "WOO_CS", "WOO_BASE_URL"):
            monkeypatch.delenv(k, raising=False)
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        assert WooCommerceAdapter().update_tracking("1001", "CJ", "12345") is False

    def test_update_tracking_dry_run(self, mock_wc_env, monkeypatch):
        """ADAPTER_DRY_RUN=1 시 True (차단)."""
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        assert WooCommerceAdapter().update_tracking("1001", "CJ", "12345") is True
