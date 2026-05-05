"""tests/test_woocommerce_adapter_real.py — WooCommerce 어댑터 HTTP mock 테스트 (Phase 131).

fetch_inventory, upload_product HTTP mock 검증.
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
def mock_wc_env(monkeypatch):
    monkeypatch.setenv("WC_KEY", "ck_test_consumer_key_value_here")
    monkeypatch.setenv("WC_SECRET", "cs_test_consumer_secret_value_here")
    monkeypatch.setenv("WC_URL", "https://myshop.example.com")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)


MOCK_WC_PRODUCTS = [
    {
        "id": 101,
        "name": "WC Yoga Legging",
        "status": "publish",
        "regular_price": "79000",
        "sku": "WC-001",
    },
    {
        "id": 102,
        "name": "WC Sports Top",
        "status": "publish",
        "regular_price": "45000",
        "sku": "WC-002",
    },
]


# ---------------------------------------------------------------------------
# 1. 기본 임포트/속성
# ---------------------------------------------------------------------------

def test_import():
    from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
    assert WooCommerceAdapter is not None


def test_marketplace_attribute():
    from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
    assert WooCommerceAdapter.marketplace == "woocommerce"


# ---------------------------------------------------------------------------
# 2. 환경변수 별칭 지원
# ---------------------------------------------------------------------------

class TestEnvAliases:
    def test_woo_ck_alias(self, monkeypatch):
        monkeypatch.setenv("WOO_CK", "ck_alias_key")
        monkeypatch.setenv("WOO_CS", "cs_alias_secret")
        monkeypatch.setenv("WOO_BASE_URL", "https://wooshop.example.com")
        monkeypatch.delenv("WC_KEY", raising=False)
        monkeypatch.delenv("WC_SECRET", raising=False)
        monkeypatch.delenv("WC_URL", raising=False)
        from src.seller_console.market_adapters.woocommerce_adapter import _api_active
        assert _api_active() is True

    def test_wc_key_alias(self, monkeypatch):
        monkeypatch.setenv("WC_KEY", "ck_wc_key")
        monkeypatch.setenv("WC_SECRET", "cs_wc_secret")
        monkeypatch.setenv("WC_URL", "https://wcshop.example.com")
        from src.seller_console.market_adapters.woocommerce_adapter import _api_active
        assert _api_active() is True

    def test_no_keys(self, monkeypatch):
        for k in ("WC_KEY", "WC_SECRET", "WC_URL", "WOO_CK", "WOO_CS", "WOO_BASE_URL"):
            monkeypatch.delenv(k, raising=False)
        from src.seller_console.market_adapters.woocommerce_adapter import _api_active
        assert _api_active() is False


# ---------------------------------------------------------------------------
# 3. fetch_inventory HTTP mock
# ---------------------------------------------------------------------------

class TestFetchInventoryMock:
    def test_fetch_success(self, mock_wc_env):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_WC_PRODUCTS
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
            adapter = WooCommerceAdapter()
            items = adapter.fetch_inventory()

        assert len(items) == 2
        assert items[0].marketplace == "woocommerce"
        assert items[0].state == "active"
        assert items[0].price_krw == 79000

    def test_fetch_http_error(self, mock_wc_env):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")

        with patch("requests.get", return_value=mock_resp):
            from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
            items = WooCommerceAdapter().fetch_inventory()
        assert items == []

    def test_fetch_no_keys(self, monkeypatch):
        for k in ("WC_KEY", "WC_SECRET", "WC_URL", "WOO_CK", "WOO_CS", "WOO_BASE_URL"):
            monkeypatch.delenv(k, raising=False)
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        assert WooCommerceAdapter().fetch_inventory() == []


# ---------------------------------------------------------------------------
# 4. upload_product HTTP mock
# ---------------------------------------------------------------------------

class TestUploadProductMock:
    def test_upload_success(self, mock_wc_env):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 999, "name": "New Product"}
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp):
            from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
            result = WooCommerceAdapter().upload_product({"name": "New Product"})

        assert result["status"] == "ok"

    def test_upload_http_error(self, mock_wc_env):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 422")

        with patch("requests.post", return_value=mock_resp):
            from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
            result = WooCommerceAdapter().upload_product({})
        assert result["status"] == "error"

    def test_upload_no_keys(self, monkeypatch):
        for k in ("WC_KEY", "WC_SECRET", "WC_URL", "WOO_CK", "WOO_CS", "WOO_BASE_URL"):
            monkeypatch.delenv(k, raising=False)
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        result = WooCommerceAdapter().upload_product({})
        assert result["status"] == "stub"

    def test_upload_dry_run(self, mock_wc_env, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        result = WooCommerceAdapter().upload_product({})
        assert result["status"] == "dry_run"


# ---------------------------------------------------------------------------
# 5. health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_missing(self, monkeypatch):
        for k in ("WC_KEY", "WC_SECRET", "WC_URL", "WOO_CK", "WOO_CS", "WOO_BASE_URL"):
            monkeypatch.delenv(k, raising=False)
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        result = WooCommerceAdapter().health_check()
        assert result["status"] == "missing"

    def test_health_dry_run(self, mock_wc_env, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        result = WooCommerceAdapter().health_check()
        assert result["status"] == "dry_run"

    def test_health_ok(self, mock_wc_env):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.get", return_value=mock_resp):
            from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
            result = WooCommerceAdapter().health_check()
        assert result["status"] == "ok"
