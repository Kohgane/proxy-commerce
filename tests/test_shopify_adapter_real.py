"""tests/test_shopify_adapter_real.py — Shopify 어댑터 HTTP mock 테스트 (Phase 131).

fetch_inventory, upload_product, fetch_orders HTTP mock 검증.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_shopify_env(monkeypatch):
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shpat_test_valid_token_value_here")
    monkeypatch.setenv("SHOPIFY_SHOP", "testshop.myshopify.com")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)


MOCK_PRODUCTS_RESPONSE = {
    "products": [
        {
            "id": 1234567890,
            "title": "Alo Yoga Legging",
            "status": "active",
            "variants": [{"price": "89000", "sku": "ALO-001"}],
        },
        {
            "id": 9876543210,
            "title": "Sports Top",
            "status": "active",
            "variants": [{"price": "55000", "sku": "TOP-001"}],
        },
    ]
}

MOCK_ORDERS_RESPONSE = {
    "orders": [
        {
            "id": 111222333,
            "name": "#1001",
            "financial_status": "paid",
            "line_items": [{"title": "Alo Yoga Legging", "quantity": 1}],
        }
    ]
}


# ---------------------------------------------------------------------------
# 1. 기본 임포트/속성
# ---------------------------------------------------------------------------

def test_import():
    from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
    assert ShopifyAdapter is not None


def test_marketplace_attribute():
    from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
    assert ShopifyAdapter.marketplace == "shopify"


# ---------------------------------------------------------------------------
# 2. fetch_inventory HTTP mock
# ---------------------------------------------------------------------------

class TestFetchInventoryMock:
    def test_fetch_inventory_success(self, mock_shopify_env):
        """HTTP 200 응답 → MarketStatusItem 목록 반환."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_PRODUCTS_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
            adapter = ShopifyAdapter()
            items = adapter.fetch_inventory()

        assert len(items) == 2
        assert items[0].marketplace == "shopify"
        assert items[0].state == "active"
        assert items[0].price_krw == 89000

    def test_fetch_inventory_http_error(self, mock_shopify_env):
        """HTTP 오류 → 빈 목록."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")

        with patch("requests.get", return_value=mock_resp):
            from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
            adapter = ShopifyAdapter()
            items = adapter.fetch_inventory()

        assert items == []

    def test_fetch_inventory_no_keys(self, monkeypatch):
        """키 미설정 → 빈 목록."""
        monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        adapter = ShopifyAdapter()
        items = adapter.fetch_inventory()
        assert items == []


# ---------------------------------------------------------------------------
# 3. upload_product HTTP mock
# ---------------------------------------------------------------------------

class TestUploadProductMock:
    def test_upload_success(self, mock_shopify_env):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"product": {"id": 999, "title": "New Product"}}
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp):
            from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
            adapter = ShopifyAdapter()
            result = adapter.upload_product({"title": "New Product", "status": "active"})

        assert result["status"] == "ok"
        assert "data" in result

    def test_upload_http_error(self, mock_shopify_env):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 422")

        with patch("requests.post", return_value=mock_resp):
            from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
            adapter = ShopifyAdapter()
            result = adapter.upload_product({"title": "Bad Product"})

        assert result["status"] == "error"

    def test_upload_no_keys(self, monkeypatch):
        monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        adapter = ShopifyAdapter()
        result = adapter.upload_product({})
        assert result["status"] == "stub"

    def test_upload_dry_run(self, mock_shopify_env, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        adapter = ShopifyAdapter()
        result = adapter.upload_product({})
        assert result["status"] == "dry_run"


# ---------------------------------------------------------------------------
# 4. health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_missing(self, monkeypatch):
        monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        result = ShopifyAdapter().health_check()
        assert result["status"] == "missing"

    def test_health_dry_run(self, mock_shopify_env, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
        result = ShopifyAdapter().health_check()
        assert result["status"] == "dry_run"

    def test_health_ok(self, mock_shopify_env):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.get", return_value=mock_resp):
            from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
            result = ShopifyAdapter().health_check()
        assert result["status"] == "ok"

    def test_health_fail(self, mock_shopify_env):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("requests.get", return_value=mock_resp):
            from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
            result = ShopifyAdapter().health_check()
        assert result["status"] == "fail"
