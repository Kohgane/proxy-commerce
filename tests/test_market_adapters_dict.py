"""tests/test_market_adapters_dict.py — 마켓 어댑터 딕셔너리 구성 테스트 (Phase 132).

- kohganemultishop 어댑터 제거 확인
- woocommerce 어댑터 등록 확인
- KohganeMultishopAdapter deprecated 경고 확인
"""
from __future__ import annotations

import os
import sys
import warnings

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 1. MarketStatusService 어댑터 딕셔너리
# ---------------------------------------------------------------------------

class TestMarketAdaptersDict:
    def test_woocommerce_in_adapters(self):
        """woocommerce 어댑터가 live_adapters에 포함됨."""
        from src.seller_console.market_status_service import MarketStatusService
        svc = MarketStatusService.__new__(MarketStatusService)
        adapters = MarketStatusService._build_live_adapters()
        assert "woocommerce" in adapters

    def test_kohganemultishop_not_in_adapters(self):
        """kohganemultishop 어댑터가 live_adapters에서 제거됨."""
        from src.seller_console.market_status_service import MarketStatusService
        adapters = MarketStatusService._build_live_adapters()
        assert "kohganemultishop" not in adapters

    def test_coupang_still_in_adapters(self):
        """coupang 어댑터는 여전히 존재."""
        from src.seller_console.market_status_service import MarketStatusService
        adapters = MarketStatusService._build_live_adapters()
        assert "coupang" in adapters

    def test_smartstore_still_in_adapters(self):
        """smartstore 어댑터는 여전히 존재."""
        from src.seller_console.market_status_service import MarketStatusService
        adapters = MarketStatusService._build_live_adapters()
        assert "smartstore" in adapters

    def test_11st_still_in_adapters(self):
        """11st 어댑터는 여전히 존재."""
        from src.seller_console.market_status_service import MarketStatusService
        adapters = MarketStatusService._build_live_adapters()
        assert "11st" in adapters


# ---------------------------------------------------------------------------
# 2. KohganeMultishopAdapter deprecated 경고
# ---------------------------------------------------------------------------

class TestKohganeMultishopDeprecated:
    def test_deprecated_warning_on_init(self):
        """KohganeMultishopAdapter 인스턴스화 시 DeprecationWarning 발생."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from src.seller_console.market_adapters.kohgane_multishop_adapter import KohganeMultishopAdapter
            KohganeMultishopAdapter()
        assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

    def test_deprecated_flag(self):
        """DEPRECATED 클래스 속성이 True."""
        from src.seller_console.market_adapters.kohgane_multishop_adapter import KohganeMultishopAdapter
        assert KohganeMultishopAdapter.DEPRECATED is True

    def test_fetch_inventory_returns_empty(self):
        """deprecated 어댑터의 fetch_inventory는 빈 리스트."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from src.seller_console.market_adapters.kohgane_multishop_adapter import KohganeMultishopAdapter
            adapter = KohganeMultishopAdapter()
        assert adapter.fetch_inventory() == []

    def test_upload_product_returns_deprecated(self):
        """deprecated 어댑터의 upload_product는 error=deprecated."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from src.seller_console.market_adapters.kohgane_multishop_adapter import KohganeMultishopAdapter
            adapter = KohganeMultishopAdapter()
        result = adapter.upload_product({})
        assert result.get("error") == "deprecated" or result.get("ok") is False

    def test_health_check_returns_deprecated(self):
        """deprecated 어댑터의 health_check는 status=deprecated."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            from src.seller_console.market_adapters.kohgane_multishop_adapter import KohganeMultishopAdapter
            adapter = KohganeMultishopAdapter()
        result = adapter.health_check()
        assert result["status"] == "deprecated"


# ---------------------------------------------------------------------------
# 3. WooCommerceAdapter 속성
# ---------------------------------------------------------------------------

class TestWooCommerceAdapterAttributes:
    def test_marketplace_name(self):
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        assert WooCommerceAdapter.marketplace == "woocommerce"

    def test_display_name(self):
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
        assert "WooCommerce" in WooCommerceAdapter.display_name
        assert "코가네" in WooCommerceAdapter.display_name
