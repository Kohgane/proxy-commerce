"""tests/test_orders_models.py — UnifiedOrder 모델 직렬화, 마스킹 함수, OrderStatus 테스트."""
from __future__ import annotations

import sys
import os
from datetime import datetime
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.seller_console.orders.models import (
    OrderLineItem,
    OrderStatus,
    UnifiedOrder,
    mask_address,
    mask_name,
    mask_phone,
)


class TestOrderStatus:
    def test_values(self):
        assert OrderStatus.NEW.value == "new"
        assert OrderStatus.SHIPPED.value == "shipped"

    def test_str_enum(self):
        assert OrderStatus.PAID.value == "paid"

    def test_all_statuses_exist(self):
        expected = {"new", "paid", "preparing", "shipped", "delivered", "canceled", "returned", "exchanged", "refund_requested"}
        assert {s.value for s in OrderStatus} == expected


class TestMaskFunctions:
    def test_mask_name_3chars(self):
        assert mask_name("홍길동") == "홍*동"

    def test_mask_name_2chars(self):
        assert mask_name("김철") == "김*"

    def test_mask_name_4chars(self):
        assert mask_name("김철수민") == "김**민"

    def test_mask_name_empty(self):
        assert mask_name("") == ""

    def test_mask_name_1char(self):
        assert mask_name("김") == "김"

    def test_mask_phone_standard(self):
        assert mask_phone("010-1234-5678") == "010-****-5678"

    def test_mask_phone_no_match(self):
        assert mask_phone("no-number") == "no-number"

    def test_mask_address_long(self):
        result = mask_address("서울시 강남구 테헤란로 123 456호")
        assert result == "서울시 강남구 ***"

    def test_mask_address_short(self):
        assert mask_address("서울시 강남구") == "서울시 강남구"

    def test_mask_address_empty(self):
        assert mask_address("") == ""


class TestOrderLineItem:
    def test_create(self):
        item = OrderLineItem(
            sku="SKU-001",
            title="테스트 상품",
            qty=2,
            unit_price_krw=Decimal("15000"),
        )
        assert item.sku == "SKU-001"
        assert item.qty == 2
        assert item.options == {}


class TestUnifiedOrder:
    def _make_order(self, **kwargs) -> UnifiedOrder:
        defaults = dict(
            order_id="TEST-001",
            marketplace="coupang",
            status=OrderStatus.PAID,
            placed_at=datetime(2024, 1, 15, 10, 30, 0),
            total_krw=Decimal("39000"),
            shipping_fee_krw=Decimal("3000"),
            items=[
                OrderLineItem(sku="SKU-A", title="상품 A", qty=1, unit_price_krw=Decimal("36000"))
            ],
        )
        defaults.update(kwargs)
        return UnifiedOrder(**defaults)

    def test_to_dict_basic(self):
        order = self._make_order()
        d = order.to_dict()
        assert d["order_id"] == "TEST-001"
        assert d["marketplace"] == "coupang"
        assert d["status"] == "paid"
        assert d["total_krw"] == "39000"
        assert d["shipping_fee_krw"] == "3000"

    def test_to_dict_items(self):
        order = self._make_order()
        d = order.to_dict()
        assert len(d["items"]) == 1
        assert d["items"][0]["sku"] == "SKU-A"
        assert d["items"][0]["qty"] == 1

    def test_to_dict_datetime_iso(self):
        order = self._make_order()
        d = order.to_dict()
        assert d["placed_at"] == "2024-01-15T10:30:00"
        assert d["paid_at"] is None

    def test_to_dict_optional_decimals(self):
        order = self._make_order(
            landed_cost_krw=Decimal("20000"),
            margin_krw=Decimal("5000"),
            margin_pct=Decimal("12.5"),
        )
        d = order.to_dict()
        assert d["landed_cost_krw"] == "20000"
        assert d["margin_pct"] == "12.5"

    def test_to_dict_none_decimals(self):
        order = self._make_order()
        d = order.to_dict()
        assert d["landed_cost_krw"] is None
        assert d["margin_krw"] is None

    def test_status_raw_string(self):
        """status가 str로 저장돼도 직렬화 동작."""
        order = self._make_order(status="shipped")
        d = order.to_dict()
        assert d["status"] == "shipped"

    def test_default_items_empty(self):
        order = UnifiedOrder(
            order_id="X",
            marketplace="smartstore",
            status=OrderStatus.NEW,
            placed_at=datetime.utcnow(),
        )
        assert order.items == []
        assert order.total_krw == Decimal(0)

    def test_notes_default_empty_string(self):
        order = self._make_order()
        assert order.notes == ""
