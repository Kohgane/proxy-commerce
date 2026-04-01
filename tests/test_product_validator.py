"""tests/test_product_validator.py — 상품 데이터 검증 테스트.

ProductValidator의 SKU 형식, 가격 범위, 번역 일관성 검증 로직을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.validation.product_validator import ProductValidator  # noqa: E402


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def validator():
    return ProductValidator()


VALID_PRODUCT = {
    "sku": "PORTER-BAG-001",
    "title": "포터 토트백",
    "title_en": "Porter Tote Bag",
    "price_krw": 150000,
    "stock": 5,
    "vendor": "porter",
    "category": "bag",
    "image_url": "https://example.com/bag.jpg",
}


# ──────────────────────────────────────────────────────────
# 단일 상품 검증 테스트
# ──────────────────────────────────────────────────────────

class TestProductValidation:
    def test_valid_product_passes(self, validator):
        """유효한 상품은 검증을 통과한다."""
        is_valid, errors = validator.validate(VALID_PRODUCT)
        assert is_valid is True
        assert errors == []

    def test_missing_sku_fails(self, validator):
        """sku 없으면 검증 실패."""
        product = {**VALID_PRODUCT}
        del product["sku"]
        is_valid, errors = validator.validate(product)
        assert is_valid is False
        assert any("sku" in e.lower() for e in errors)

    def test_invalid_sku_format_fails(self, validator):
        """SKU 형식이 잘못되면 검증 실패."""
        product = {**VALID_PRODUCT, "sku": "INVALID"}  # 하이픈 없음
        is_valid, errors = validator.validate(product)
        assert is_valid is False
        assert any("SKU" in e for e in errors)

    def test_valid_sku_formats(self, validator):
        """다양한 유효한 SKU 형식을 허용한다."""
        valid_skus = [
            "PORTER-BAG-001",
            "MEMO-PERFUME-023",
            "VENDOR-CATEGORY",
            "A1-B2-C3",
        ]
        for sku in valid_skus:
            product = {**VALID_PRODUCT, "sku": sku}
            _, errors = validator.validate(product)
            sku_errors = [e for e in errors if "SKU" in e]
            assert sku_errors == [], f"SKU '{sku}'이 유효해야 하는데 오류: {sku_errors}"

    def test_negative_price_fails(self, validator):
        """음수 가격은 검증 실패."""
        product = {**VALID_PRODUCT, "price_krw": -1000}
        is_valid, errors = validator.validate(product)
        assert is_valid is False
        assert any("음수" in e for e in errors)

    def test_zero_price_fails(self, validator):
        """0원 가격은 검증 실패."""
        product = {**VALID_PRODUCT, "price_krw": 0}
        is_valid, errors = validator.validate(product)
        assert is_valid is False
        assert any("0원" in e for e in errors)

    def test_extremely_large_price_fails(self, validator):
        """이상치 가격은 검증 실패."""
        product = {**VALID_PRODUCT, "price_krw": 999_999_999}
        is_valid, errors = validator.validate(product)
        assert is_valid is False

    def test_missing_image_warning(self, validator):
        """이미지 없는 상품은 경고가 포함된다."""
        product = {**VALID_PRODUCT}
        del product["image_url"]
        is_valid, errors = validator.validate(product)
        # 이미지 경고만 있으면 is_valid=False (경고도 errors에 포함)
        assert any("이미지" in e for e in errors)

    def test_identical_ko_en_titles_fail(self, validator):
        """한국어와 영어 제목이 동일하면 번역 오류."""
        product = {**VALID_PRODUCT, "title": "Porter Bag", "title_en": "Porter Bag"}
        is_valid, errors = validator.validate(product)
        assert is_valid is False
        assert any("번역" in e for e in errors)

    def test_missing_title_fails(self, validator):
        """title 없으면 번역 오류."""
        product = {**VALID_PRODUCT}
        del product["title"]
        is_valid, errors = validator.validate(product)
        assert is_valid is False


# ──────────────────────────────────────────────────────────
# 배치 검증 테스트
# ──────────────────────────────────────────────────────────

class TestBatchValidation:
    def test_batch_returns_all_results(self, validator):
        """배치 검증이 모든 상품 결과를 반환한다."""
        products = [
            VALID_PRODUCT,
            {**VALID_PRODUCT, "price_krw": -100, "sku": "TEST-PROD-002"},
        ]
        results = validator.validate_batch(products)
        assert len(results) == 2
        assert results[0][1] is True   # 첫 번째 유효
        assert results[1][1] is False  # 두 번째 음수 가격

    def test_batch_includes_index(self, validator):
        """배치 결과에 인덱스가 포함된다."""
        products = [VALID_PRODUCT]
        results = validator.validate_batch(products)
        assert results[0][0] == 0  # 인덱스 0
