"""tests/test_orders_adapters.py — 마켓 어댑터 fetch_orders_unified / update_tracking 테스트."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.seller_console.orders.models import OrderStatus, UnifiedOrder


# ---------------------------------------------------------------------------
# CoupangAdapter
# ---------------------------------------------------------------------------

class TestCoupangOrdersUnified:
    def test_stub_returns_3_mock_orders(self, monkeypatch):
        """API 키 미설정 → mock 3건 반환."""
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        orders = CoupangAdapter().fetch_orders_unified()
        assert len(orders) == 3
        assert all(isinstance(o, UnifiedOrder) for o in orders)
        assert all(o.marketplace == "coupang" for o in orders)

    def test_stub_orders_have_realistic_statuses(self, monkeypatch):
        """mock 주문 상태 확인."""
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        orders = CoupangAdapter().fetch_orders_unified()
        statuses = {o.status for o in orders}
        assert statuses & {OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.SHIPPED}

    def test_stub_orders_have_masked_info(self, monkeypatch):
        """mock 주문 개인정보 마스킹 확인."""
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        orders = CoupangAdapter().fetch_orders_unified()
        for o in orders:
            if o.buyer_name_masked:
                assert "*" in o.buyer_name_masked

    def test_dry_run_returns_empty(self, monkeypatch):
        """ADAPTER_DRY_RUN=1 → 빈 목록 반환."""
        monkeypatch.setenv("COUPANG_VENDOR_ID", "V001")
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "AK001")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "SK001")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        orders = CoupangAdapter().fetch_orders_unified()
        assert orders == []
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_update_tracking_dry_run(self, monkeypatch):
        """ADAPTER_DRY_RUN=1 → True 반환 (API 미호출)."""
        monkeypatch.setenv("COUPANG_VENDOR_ID", "V001")
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "AK001")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "SK001")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        result = CoupangAdapter().update_tracking("ORDER-001", courier="CJ", tracking_no="123456")
        assert result is True
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_update_tracking_no_api_keys(self, monkeypatch):
        """API 키 없음 → False 반환."""
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)

        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        result = CoupangAdapter().update_tracking("ORDER-001", courier="CJ", tracking_no="123456")
        assert result is False


# ---------------------------------------------------------------------------
# SmartStoreAdapter
# ---------------------------------------------------------------------------

class TestSmartStoreOrdersUnified:
    def test_no_api_returns_empty(self, monkeypatch):
        """API 키 미설정 → 빈 목록."""
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_SECRET", raising=False)

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        orders = SmartStoreAdapter().fetch_orders_unified()
        assert orders == []

    def test_dry_run_returns_empty(self, monkeypatch):
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "NAVER_ID")
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "NAVER_SECRET")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        orders = SmartStoreAdapter().fetch_orders_unified()
        assert orders == []
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_backward_compat_fetch_orders(self, monkeypatch):
        """구 fetch_orders()가 내부적으로 동작 확인."""
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_SECRET", raising=False)

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        result = SmartStoreAdapter().fetch_orders()
        assert isinstance(result, list)

    def test_update_tracking_dry_run(self, monkeypatch):
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "NAVER_ID")
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "NAVER_SECRET")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        result = SmartStoreAdapter().update_tracking("ORDER-001", courier="CJ", tracking_no="123456")
        assert result is True
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_update_tracking_no_keys(self, monkeypatch):
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_COMMERCE_CLIENT_SECRET", raising=False)

        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        result = SmartStoreAdapter().update_tracking("ORDER-001", courier="CJ", tracking_no="123456")
        assert result is False


# ---------------------------------------------------------------------------
# ElevenAdapter
# ---------------------------------------------------------------------------

class TestElevenOrdersUnified:
    def test_no_api_returns_empty(self, monkeypatch):
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        orders = ElevenAdapter().fetch_orders_unified()
        assert orders == []

    def test_dry_run_returns_empty(self, monkeypatch):
        monkeypatch.setenv("ELEVENST_API_KEY", "ELEVEN_KEY")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        orders = ElevenAdapter().fetch_orders_unified()
        assert orders == []
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_backward_compat_fetch_orders(self, monkeypatch):
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        result = ElevenAdapter().fetch_orders()
        assert isinstance(result, list)

    def test_parse_orders_xml(self):
        """XML 파싱 → UnifiedOrder 목록."""
        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        xml = """<OrderList>
            <Order>
                <ordNo>11ST-001</ordNo>
                <ordStatus>PAYMENT_DONE</ordStatus>
                <ordDt>20240115</ordDt>
                <buyerNm>홍길동</buyerNm>
                <buyerTel>010-1234-5678</buyerTel>
                <dlvrAdrs>서울시 강남구 테헤란로 123</dlvrAdrs>
                <prdNm>테스트 상품</prdNm>
                <ordQty>2</ordQty>
                <ordAmt>39000</ordAmt>
                <prdCd>SKU-001</prdCd>
            </Order>
        </OrderList>"""
        adapter = ElevenAdapter()
        orders = adapter._parse_orders_xml(xml)
        assert len(orders) == 1
        assert orders[0].order_id == "11ST-001"
        assert orders[0].marketplace == "11st"
        assert orders[0].status == OrderStatus.PAID
        assert "*" in (orders[0].buyer_name_masked or "")

    def test_update_tracking_dry_run(self, monkeypatch):
        monkeypatch.setenv("ELEVENST_API_KEY", "ELEVEN_KEY")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        result = ElevenAdapter().update_tracking("ORDER-001", courier="04", tracking_no="123456")
        assert result is True
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_update_tracking_no_key(self, monkeypatch):
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)

        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        result = ElevenAdapter().update_tracking("ORDER-001", courier="04", tracking_no="123456")
        assert result is False


# ---------------------------------------------------------------------------
# KohganeMultishopAdapter
# ---------------------------------------------------------------------------

class TestKohganeMultishopOrdersUnified:
    def test_fetch_orders_unified_stub(self):
        from src.seller_console.market_adapters.kohgane_multishop_adapter import KohganeMultishopAdapter
        orders = KohganeMultishopAdapter().fetch_orders_unified()
        assert orders == []

    def test_update_tracking_stub(self):
        from src.seller_console.market_adapters.kohgane_multishop_adapter import KohganeMultishopAdapter
        result = KohganeMultishopAdapter().update_tracking("ORDER-001", courier="CJ", tracking_no="123456")
        assert result is False
