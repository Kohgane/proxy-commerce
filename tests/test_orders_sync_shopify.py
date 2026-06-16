"""tests/test_orders_sync_shopify.py — Shopify 주문수집·배송추적 (Phase 206).

- OrderSyncService.adapters에 shopify 포함
- ShopifyAdapter.fetch_orders_unified GraphQL mock 검증 + 상태 매핑
- update_tracking: fulfillmentOrders 조회 → fulfillmentCreateV2 성공/실패/userErrors
- 자격증명 미설정·ADAPTER_DRY_RUN 안전 처리
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _resp(status_code: int, payload: dict):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = payload
    return r


MOCK_ORDERS_PAGE = {
    "data": {
        "orders": {
            "edges": [
                {
                    "node": {
                        "id": "gid://shopify/Order/450789469",
                        "name": "#1001",
                        "createdAt": "2026-06-10T10:00:00Z",
                        "processedAt": "2026-06-10T10:05:00Z",
                        "cancelledAt": None,
                        "displayFinancialStatus": "PAID",
                        "displayFulfillmentStatus": "UNFULFILLED",
                        "totalPriceSet": {"shopMoney": {"amount": "79000", "currencyCode": "KRW"}},
                        "totalShippingPriceSet": {"shopMoney": {"amount": "3000"}},
                        "customer": {"firstName": "철", "lastName": "수"},
                        "shippingAddress": {"phone": "010-1234-5678", "city": "서울"},
                        "lineItems": {
                            "edges": [
                                {"node": {"sku": "SHP-1", "title": "테스트 상품", "quantity": 2,
                                          "originalUnitPriceSet": {"shopMoney": {"amount": "38000"}}}}
                            ]
                        },
                    }
                }
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": "c1"},
        }
    }
}


# ---------------------------------------------------------------------------
# 1. OrderSyncService 등록
# ---------------------------------------------------------------------------

class TestSyncServiceRegistration:
    def test_shopify_in_adapters(self):
        with patch("src.seller_console.orders.sheets_adapter.OrderSheetsAdapter") as MockSheets:
            MockSheets.return_value = MagicMock()
            from src.seller_console.orders.sync_service import OrderSyncService
            svc = OrderSyncService()
        assert "shopify" in svc.adapters


# ---------------------------------------------------------------------------
# 2. fetch_orders_unified
# ---------------------------------------------------------------------------

class TestShopifyOrdersFetch:
    @pytest.fixture
    def configured(self, monkeypatch):
        monkeypatch.setenv("SHOPIFY_SHOP", "testshop.myshopify.com")
        monkeypatch.setenv("SHOPIFY_CLIENT_ID", "cid_test")
        monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "shpss_test")
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_fetch_orders_unified_mock(self, configured):
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        adapter = ShopifyAdapter()
        with patch.object(adapter, "_market") as m:
            m.return_value.is_configured.return_value = True
            m.return_value.graphql.return_value = _resp(200, MOCK_ORDERS_PAGE)
            orders = adapter.fetch_orders_unified()

        assert len(orders) == 1
        o = orders[0]
        assert o["order_id"] == "450789469"
        assert o["marketplace"] == "shopify"
        assert o["status"] == "paid"  # PAID + UNFULFILLED
        assert o["total_krw"] == "79000"
        assert o["order_name"] == "#1001"
        assert o["currency"] == "KRW"
        assert len(o["items"]) == 1
        assert o["items"][0]["sku"] == "SHP-1"
        assert o["items"][0]["qty"] == 2
        # 마스킹 검증
        assert o["buyer_phone_masked"].endswith("****")
        assert o["buyer_name_masked"][0] == "철"

    def test_fetch_orders_not_configured(self, monkeypatch):
        for k in ("SHOPIFY_SHOP", "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET",
                  "SHOPIFY_AUTO_TOKEN", "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_ADMIN_TOKEN"):
            monkeypatch.delenv(k, raising=False)
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        assert ShopifyAdapter().fetch_orders_unified() == []

    def test_fetch_orders_dry_run(self, configured, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        assert ShopifyAdapter().fetch_orders_unified() == []

    def test_fetch_orders_graphql_error_returns_empty(self, configured):
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        adapter = ShopifyAdapter()
        with patch.object(adapter, "_market") as m:
            m.return_value.is_configured.return_value = True
            m.return_value.graphql.return_value = _resp(200, {"errors": [{"message": "access denied"}]})
            assert adapter.fetch_orders_unified() == []

    def test_status_mapping(self):
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        a = ShopifyAdapter()
        assert a._map_order_status("PAID", "UNFULFILLED", False) == "paid"
        assert a._map_order_status("PAID", "FULFILLED", False) == "delivered"
        assert a._map_order_status("REFUNDED", "FULFILLED", False) == "returned"
        assert a._map_order_status("PAID", "FULFILLED", True) == "canceled"
        assert a._map_order_status("PENDING", "UNFULFILLED", False) == "new"


# ---------------------------------------------------------------------------
# 3. update_tracking
# ---------------------------------------------------------------------------

FO_PAGE = {
    "data": {"order": {"fulfillmentOrders": {"edges": [
        {"node": {"id": "gid://shopify/FulfillmentOrder/77", "status": "OPEN"}}
    ]}}}
}
FULFILL_OK = {"data": {"fulfillmentCreateV2": {"fulfillment": {"id": "gid://shopify/Fulfillment/9", "status": "SUCCESS"}, "userErrors": []}}}
FULFILL_ERR = {"data": {"fulfillmentCreateV2": {"fulfillment": None, "userErrors": [{"field": ["x"], "message": "bad"}]}}}


class TestShopifyUpdateTracking:
    @pytest.fixture
    def configured(self, monkeypatch):
        monkeypatch.setenv("SHOPIFY_SHOP", "testshop.myshopify.com")
        monkeypatch.setenv("SHOPIFY_CLIENT_ID", "cid_test")
        monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "shpss_test")
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_update_tracking_success(self, configured):
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        adapter = ShopifyAdapter()
        with patch.object(adapter, "_market") as m:
            m.return_value.is_configured.return_value = True
            m.return_value.graphql.side_effect = [_resp(200, FO_PAGE), _resp(200, FULFILL_OK)]
            assert adapter.update_tracking("450789469", "CJ대한통운", "12345678") is True

    def test_update_tracking_user_errors(self, configured):
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        adapter = ShopifyAdapter()
        with patch.object(adapter, "_market") as m:
            m.return_value.is_configured.return_value = True
            m.return_value.graphql.side_effect = [_resp(200, FO_PAGE), _resp(200, FULFILL_ERR)]
            assert adapter.update_tracking("450789469", "CJ", "123") is False

    def test_update_tracking_no_fulfillment_orders(self, configured):
        empty = {"data": {"order": {"fulfillmentOrders": {"edges": []}}}}
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        adapter = ShopifyAdapter()
        with patch.object(adapter, "_market") as m:
            m.return_value.is_configured.return_value = True
            m.return_value.graphql.return_value = _resp(200, empty)
            assert adapter.update_tracking("450789469", "CJ", "123") is False

    def test_update_tracking_not_configured(self, monkeypatch):
        for k in ("SHOPIFY_SHOP", "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET",
                  "SHOPIFY_AUTO_TOKEN", "SHOPIFY_ACCESS_TOKEN", "SHOPIFY_ADMIN_TOKEN"):
            monkeypatch.delenv(k, raising=False)
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        assert ShopifyAdapter().update_tracking("1", "CJ", "123") is False

    def test_update_tracking_dry_run(self, configured, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        assert ShopifyAdapter().update_tracking("1", "CJ", "123") is True
