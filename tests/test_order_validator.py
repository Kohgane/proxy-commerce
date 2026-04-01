"""tests/test_order_validator.py — 주문 데이터 검증 테스트.

OrderValidator의 Shopify/WooCommerce 페이로드 검증 로직을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.validation.order_validator import OrderValidator  # noqa: E402


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def validator():
    return OrderValidator()


VALID_SHOPIFY_ORDER = {
    "id": 12345,
    "order_number": 1001,
    "email": "customer@example.com",
    "total_price": "59000",
    "currency": "KRW",
    "financial_status": "paid",
    "line_items": [
        {"id": 1, "title": "테스트 상품", "quantity": 1, "price": "59000"},
    ],
}

VALID_WOO_ORDER = {
    "id": 9876,
    "total": "89000",
    "currency": "KRW",
    "status": "processing",
    "line_items": [
        {"product_id": 100, "quantity": 2, "total": "89000"},
    ],
}


# ──────────────────────────────────────────────────────────
# Shopify 검증 테스트
# ──────────────────────────────────────────────────────────

class TestShopifyOrderValidation:
    def test_valid_order_passes(self, validator):
        """유효한 Shopify 주문은 검증을 통과한다."""
        is_valid, errors = validator.validate_shopify(VALID_SHOPIFY_ORDER)
        assert is_valid is True
        assert errors == []

    def test_missing_id_fails(self, validator):
        """id 필드 없으면 검증 실패."""
        order = {**VALID_SHOPIFY_ORDER}
        del order["id"]
        is_valid, errors = validator.validate_shopify(order)
        assert is_valid is False
        assert any("id" in e for e in errors)

    def test_empty_line_items_fails(self, validator):
        """line_items가 비어 있으면 검증 실패."""
        order = {**VALID_SHOPIFY_ORDER, "line_items": []}
        is_valid, errors = validator.validate_shopify(order)
        assert is_valid is False
        assert any("line_items" in e for e in errors)

    def test_negative_price_fails(self, validator):
        """음수 가격은 검증 실패."""
        order = {**VALID_SHOPIFY_ORDER, "total_price": "-1000"}
        is_valid, errors = validator.validate_shopify(order)
        assert is_valid is False
        assert any("음수" in e for e in errors)

    def test_invalid_quantity_fails(self, validator):
        """수량이 0 이하이면 검증 실패."""
        order = {**VALID_SHOPIFY_ORDER, "line_items": [
            {"id": 1, "quantity": 0, "price": "1000"},
        ]}
        is_valid, errors = validator.validate_shopify(order)
        assert is_valid is False

    def test_excessively_large_price_fails(self, validator):
        """이상치 금액(1억 초과)은 검증 실패."""
        order = {**VALID_SHOPIFY_ORDER, "total_price": "200000000"}
        is_valid, errors = validator.validate_shopify(order)
        assert is_valid is False
        assert any("이상치" in e for e in errors)

    def test_invalid_financial_status_fails(self, validator):
        """허용되지 않은 financial_status 값은 검증 실패."""
        order = {**VALID_SHOPIFY_ORDER, "financial_status": "unknown_status"}
        is_valid, errors = validator.validate_shopify(order)
        assert is_valid is False

    def test_duplicate_order_detected(self, validator):
        """동일 order_id의 두 번째 요청은 중복으로 감지된다."""
        from src.validation.order_validator import DUPLICATE_ORDER_TAG
        validator.validate_shopify(VALID_SHOPIFY_ORDER)
        is_valid2, errors2 = validator.validate_shopify(VALID_SHOPIFY_ORDER)
        assert is_valid2 is False
        assert any(e.startswith(DUPLICATE_ORDER_TAG) for e in errors2)

    def test_reset_clears_duplicate_cache(self, validator):
        """reset_duplicate_cache() 후 동일 주문을 다시 처리할 수 있다."""
        validator.validate_shopify(VALID_SHOPIFY_ORDER)
        validator.reset_duplicate_cache()
        is_valid, errors = validator.validate_shopify(VALID_SHOPIFY_ORDER)
        assert is_valid is True


# ──────────────────────────────────────────────────────────
# WooCommerce 검증 테스트
# ──────────────────────────────────────────────────────────

class TestWooCommerceOrderValidation:
    def test_valid_woo_order_passes(self, validator):
        """유효한 WooCommerce 주문은 검증을 통과한다."""
        is_valid, errors = validator.validate_woocommerce(VALID_WOO_ORDER)
        assert is_valid is True
        assert errors == []

    def test_missing_id_fails(self, validator):
        """id 필드 없으면 검증 실패."""
        order = {**VALID_WOO_ORDER}
        del order["id"]
        is_valid, errors = validator.validate_woocommerce(order)
        assert is_valid is False

    def test_woo_duplicate_detection(self, validator):
        """WooCommerce 주문도 중복 감지된다."""
        from src.validation.order_validator import DUPLICATE_ORDER_TAG
        validator.validate_woocommerce(VALID_WOO_ORDER)
        is_valid2, errors2 = validator.validate_woocommerce(VALID_WOO_ORDER)
        assert is_valid2 is False
        assert any(e.startswith(DUPLICATE_ORDER_TAG) for e in errors2)
