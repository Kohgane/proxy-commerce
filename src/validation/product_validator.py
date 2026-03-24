"""src/validation/product_validator.py — 상품 데이터 검증.

카탈로그 동기화 전 상품 데이터의 무결성을 검증한다:
  - SKU 형식 검증 (VENDOR-CATEGORY-NUM)
  - 가격 범위 검증 (음수, 0, 이상치 탐지)
  - 필수 이미지/설명 존재 여부
  - 번역 데이터 일관성 체크

환경변수:
  PRODUCT_VALIDATION_ENABLED — 검증 활성화 여부 (기본 "1")
  PRODUCT_MIN_PRICE_KRW      — 최소 허용 가격 (기본 100)
  PRODUCT_MAX_PRICE_KRW      — 최대 허용 가격 이상치 임계값 (기본 100000000)
"""

import logging
import os
import re
from typing import Any, Dict, List, Tuple

from .schemas import PRODUCT_SCHEMA, validate_schema

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("PRODUCT_VALIDATION_ENABLED", "1") == "1"
_MIN_PRICE = float(os.getenv("PRODUCT_MIN_PRICE_KRW", "100"))
_MAX_PRICE = float(os.getenv("PRODUCT_MAX_PRICE_KRW", "100000000"))

# SKU 형식: 영문/숫자 + 하이픈 구분 최소 2부분 (예: PORTER-BAG-001, MEMO-PERFUME-023)
_SKU_PATTERN = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+){1,}$", re.IGNORECASE)


class ProductValidator:
    """상품 데이터 검증기.

    사용 예:
        validator = ProductValidator()
        is_valid, errors = validator.validate(product_dict)
    """

    # ── 공개 API ──────────────────────────────────────────

    def validate(self, product: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """단일 상품 딕셔너리를 검증한다.

        Args:
            product: 상품 데이터 딕셔너리

        Returns:
            (is_valid, errors): 유효 여부와 오류 메시지 목록
        """
        if not _ENABLED:
            return True, []

        errors: List[str] = []

        # 1) 기본 스키마 검증
        _, schema_errors = validate_schema(product, PRODUCT_SCHEMA)
        errors.extend(schema_errors)

        # 2) SKU 형식 검증
        sku = product.get("sku", "")
        if sku:
            sku_errors = self._validate_sku(sku)
            errors.extend(sku_errors)

        # 3) 가격 범위 검증
        price = product.get("price_krw")
        if price is not None:
            price_errors = self._validate_price(price)
            errors.extend(price_errors)

        # 4) 이미지 존재 여부 (선택적 경고)
        image_warnings = self._check_image(product)
        errors.extend(image_warnings)

        # 5) 번역 일관성 검증
        trans_errors = self._validate_translations(product)
        errors.extend(trans_errors)

        is_valid = len(errors) == 0
        if not is_valid:
            logger.debug("상품 검증 실패 (sku=%s): %s", product.get("sku"), errors)

        return is_valid, errors

    def validate_batch(self, products: List[Dict[str, Any]]) -> List[Tuple[int, bool, List[str]]]:
        """여러 상품을 일괄 검증한다.

        Args:
            products: 상품 딕셔너리 목록

        Returns:
            [(index, is_valid, errors), ...] 형식의 결과 목록
        """
        results = []
        for i, product in enumerate(products):
            is_valid, errors = self.validate(product)
            results.append((i, is_valid, errors))
        return results

    # ── 내부 검증 메서드 ──────────────────────────────────

    def _validate_sku(self, sku: str) -> List[str]:
        """SKU 형식을 검증한다."""
        if not _SKU_PATTERN.match(sku):
            return [
                f"SKU 형식 오류: '{sku}' — 'VENDOR-CATEGORY-NUM' 형식이어야 합니다 (예: PORTER-BAG-001)"
            ]
        return []

    def _validate_price(self, price: Any) -> List[str]:
        """가격 범위를 검증한다."""
        errors: List[str] = []
        try:
            price_val = float(price)
        except (ValueError, TypeError):
            return [f"가격 파싱 실패: '{price}'"]

        if price_val < 0:
            errors.append(f"가격 범위 오류: {price_val} (음수 불허)")
        elif price_val == 0:
            errors.append(f"가격 범위 오류: {price_val} (0원 불허)")
        elif price_val < _MIN_PRICE:
            errors.append(f"가격 이상치 감지: {price_val} (최소 {_MIN_PRICE}원 미만)")
        elif price_val > _MAX_PRICE:
            errors.append(f"가격 이상치 감지: {price_val} (최대 {_MAX_PRICE}원 초과)")
        return errors

    def _check_image(self, product: Dict[str, Any]) -> List[str]:
        """이미지 URL 존재 여부를 확인한다 (경고성 검증)."""
        image = product.get("image_url") or product.get("image")
        if not image:
            return [f"경고: 상품 이미지 없음 (sku={product.get('sku', 'N/A')})"]
        return []

    def _validate_translations(self, product: Dict[str, Any]) -> List[str]:
        """번역 데이터 일관성을 확인한다."""
        errors: List[str] = []
        title_ko = product.get("title") or product.get("title_ko")
        title_en = product.get("title_en")

        # 한국어 제목은 필수
        if not title_ko:
            errors.append("번역 오류: 한국어 제목(title/title_ko)이 없습니다")

        # 영어 제목이 있으면 한국어와 동일하지 않아야 함 (번역 누락 감지)
        if title_ko and title_en and title_ko.strip() == title_en.strip():
            errors.append(
                f"번역 일관성 경고: 한국어와 영어 제목이 동일합니다 (title='{title_ko}')"
            )

        return errors
