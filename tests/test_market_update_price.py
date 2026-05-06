"""tests/test_market_update_price.py — 4개 마켓 어댑터 update_price() 테스트 (Phase 136)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestWooCommerceUpdatePrice:
    def test_dry_run_returns_false(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        monkeypatch.setenv("WC_KEY", "ck_test")
        monkeypatch.setenv("WC_SECRET", "cs_test")
        monkeypatch.setenv("WC_URL", "https://test.example.com")

        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        adapter = WooCommerceAdapter()
        result = adapter.update_price("SKU-001", 39000)
        assert result["updated"] is False
        assert result.get("_dry_run") is True

    def test_missing_credentials_returns_false(self, monkeypatch):
        monkeypatch.delenv("WC_KEY", raising=False)
        monkeypatch.delenv("WOO_CK", raising=False)
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")

        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        adapter = WooCommerceAdapter()
        result = adapter.update_price("SKU-001", 39000)
        assert result["updated"] is False
        assert result.get("reason") == "missing_credentials"

    def test_product_not_found(self, monkeypatch):
        monkeypatch.setenv("WC_KEY", "ck_test")
        monkeypatch.setenv("WC_SECRET", "cs_test")
        monkeypatch.setenv("WC_URL", "https://test.example.com")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = []  # 빈 목록
            mock_get.return_value = mock_resp

            from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
            adapter = WooCommerceAdapter()
            result = adapter.update_price("NONEXISTENT-SKU", 39000)

        assert result["updated"] is False
        assert result.get("reason") == "product_not_found"

    def test_successful_update(self, monkeypatch):
        monkeypatch.setenv("WC_KEY", "ck_test")
        monkeypatch.setenv("WC_SECRET", "cs_test")
        monkeypatch.setenv("WC_URL", "https://test.example.com")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")

        with patch("requests.get") as mock_get, patch("requests.put") as mock_put:
            # find product
            get_resp = MagicMock()
            get_resp.status_code = 200
            get_resp.json.return_value = [{"id": 123, "sku": "SKU-001"}]
            mock_get.return_value = get_resp

            # update price
            put_resp = MagicMock()
            put_resp.status_code = 200
            put_resp.json.return_value = {"id": 123, "regular_price": "39000"}
            mock_put.return_value = put_resp

            from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
            adapter = WooCommerceAdapter()
            result = adapter.update_price("SKU-001", 39000)

        assert result["updated"] is True
        assert result["price"] == 39000
        assert result["product_id"] == 123


class TestSmartstoreUpdatePrice:
    def test_dry_run_returns_false(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "test_id")
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "test_sec")

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        adapter = SmartStoreAdapter()
        result = adapter.update_price("SKU-001", 55000)
        assert result["updated"] is False
        assert result.get("_dry_run") is True

    def test_missing_credentials(self, monkeypatch):
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        adapter = SmartStoreAdapter()
        result = adapter.update_price("SKU-001", 55000)
        assert result["updated"] is False
        assert result["reason"] == "missing_credentials"


class TestElevenAdapterUpdatePrice:
    def test_dry_run_returns_false(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        monkeypatch.setenv("ELEVENST_API_KEY", "test_key")

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        adapter = ElevenAdapter()
        result = adapter.update_price("SKU-001", 45000)
        assert result["updated"] is False
        assert result.get("_dry_run") is True

    def test_missing_credentials(self, monkeypatch):
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        adapter = ElevenAdapter()
        result = adapter.update_price("SKU-001", 45000)
        assert result["updated"] is False
        assert result["reason"] == "missing_credentials"

    def test_successful_update(self, monkeypatch):
        monkeypatch.setenv("ELEVENST_API_KEY", "test_key")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")

        with patch("requests.post") as mock_post:
            resp = MagicMock()
            resp.status_code = 200
            resp.text = "<Response><code>200</code></Response>"
            mock_post.return_value = resp

            from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
            adapter = ElevenAdapter()
            result = adapter.update_price("P001", 45000)

        assert result["updated"] is True
        assert result["price"] == 45000


class TestCoupangUpdatePrice:
    def test_dry_run_returns_false(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        monkeypatch.setenv("COUPANG_VENDOR_ID", "A001")
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "ak")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "sk")

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        adapter = CoupangAdapter()
        result = adapter.update_price("SKU-001", 60000)
        assert result["updated"] is False
        assert result.get("_dry_run") is True

    def test_missing_credentials(self, monkeypatch):
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        adapter = CoupangAdapter()
        result = adapter.update_price("SKU-001", 60000)
        assert result["updated"] is False
        assert result["reason"] == "missing_credentials"
