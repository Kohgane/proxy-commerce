"""tests/test_market_adapters_phase128.py — 마켓 어댑터 Phase 128 테스트.

각 어댑터 stub 응답 + dry-run 모드 + health_check.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# CoupangAdapter
# ---------------------------------------------------------------------------

class TestCoupangAdapter:
    def test_import(self):
        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        assert CoupangAdapter.marketplace == "coupang"

    def test_fetch_inventory_stub_without_api_keys(self, monkeypatch):
        """API 키 없으면 빈 리스트 반환."""
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        adapter = CoupangAdapter()
        result = adapter.fetch_inventory()
        assert result == []

    def test_health_check_missing_without_keys(self, monkeypatch):
        """API 키 없으면 health_check status='missing'."""
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        result = CoupangAdapter().health_check()
        assert result["status"] == "missing"
        assert "hint" in result

    def test_upload_product_stub_without_keys(self, monkeypatch):
        """API 키 없으면 stub 응답 반환."""
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        result = CoupangAdapter().upload_product({})
        assert result["status"] == "stub"

    def test_dry_run_mode(self, monkeypatch):
        """ADAPTER_DRY_RUN=1 이면 dry_run 응답."""
        monkeypatch.setenv("COUPANG_VENDOR_ID", "V001test")
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "AK001test")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "SK001test")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")

        from src.seller_console.market_adapters import coupang_adapter
        # 모듈 캐시 초기화를 위해 함수를 직접 호출
        result = coupang_adapter.CoupangAdapter().upload_product({})
        assert result["status"] == "dry_run"

        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_hmac_sign_generates_auth_header(self, monkeypatch):
        """HMAC 서명 헤더 생성 확인."""
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "test_access_key")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "test_secret_key")

        from src.seller_console.market_adapters.coupang_adapter import _hmac_sign
        headers = _hmac_sign("GET", "/v2/test/path")
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("CEA algorithm=HmacSHA256")


# ---------------------------------------------------------------------------
# SmartStoreAdapter
# ---------------------------------------------------------------------------

class TestSmartStoreAdapter:
    def test_import(self):
        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        assert SmartStoreAdapter.marketplace == "smartstore"

    def test_fetch_inventory_stub_without_keys(self, monkeypatch):
        """API 키 없으면 빈 리스트."""
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_SECRET", raising=False)

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        result = SmartStoreAdapter().fetch_inventory()
        assert result == []

    def test_health_check_missing_without_keys(self, monkeypatch):
        """API 키 없으면 status='missing'."""
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_SECRET", raising=False)

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        result = SmartStoreAdapter().health_check()
        assert result["status"] == "missing"

    def test_upload_product_stub_without_keys(self, monkeypatch):
        """API 키 없으면 stub 응답."""
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_SECRET", raising=False)

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        result = SmartStoreAdapter().upload_product({})
        assert result["status"] == "stub"

    def test_dry_run_mode(self, monkeypatch):
        """ADAPTER_DRY_RUN=1 이면 dry_run 응답."""
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "naver_client_id")
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "naver_secret")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        result = SmartStoreAdapter().upload_product({})
        assert result["status"] == "dry_run"

        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)


# ---------------------------------------------------------------------------
# ElevenAdapter
# ---------------------------------------------------------------------------

class TestElevenAdapter:
    def test_import(self):
        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        assert ElevenAdapter.marketplace == "11st"

    def test_fetch_inventory_stub_without_key(self, monkeypatch):
        """API 키 없으면 빈 리스트."""
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        result = ElevenAdapter().fetch_inventory()
        assert result == []

    def test_health_check_missing_without_key(self, monkeypatch):
        """API 키 없으면 status='missing'."""
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        result = ElevenAdapter().health_check()
        assert result["status"] == "missing"

    def test_upload_product_stub_without_key(self, monkeypatch):
        """API 키 없으면 stub 응답."""
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        result = ElevenAdapter().upload_product({})
        assert result["status"] == "stub"

    def test_dry_run_mode(self, monkeypatch):
        """ADAPTER_DRY_RUN=1 이면 dry_run 응답."""
        monkeypatch.setenv("ELEVENST_API_KEY", "test_eleven_api_key")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        result = ElevenAdapter().upload_product({})
        assert result["status"] == "dry_run"

        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_parse_xml_products_empty_xml(self):
        """빈 XML 파싱 → 빈 리스트."""
        from src.seller_console.market_adapters.eleven_adapter import _parse_xml_products
        result = _parse_xml_products("<Products></Products>")
        assert result == []

    def test_parse_xml_products_with_data(self):
        """XML 상품 데이터 파싱."""
        from src.seller_console.market_adapters.eleven_adapter import _parse_xml_products
        xml = """<Products>
        <Product>
            <productCode>P001</productCode>
            <productName>테스트 상품</productName>
            <sellprc>50000</sellprc>
            <productStatusCode>01</productStatusCode>
        </Product>
        </Products>"""
        result = _parse_xml_products(xml)
        assert len(result) == 1
        assert result[0].product_id == "P001"
        assert result[0].state == "active"
        assert result[0].price_krw == 50000
