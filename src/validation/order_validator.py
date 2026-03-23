"""src/validation/order_validator.py — 주문 데이터 검증.

Shopify/WooCommerce 웹훅 페이로드의 스키마 검증, 필수 필드 확인,
금액/수량 범위 검증, 중복 주문 감지를 수행한다.

환경변수:
  ORDER_VALIDATION_ENABLED — 검증 활성화 여부 (기본 "1")
"""

import logging
import os
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from .schemas import ORDER_SCHEMA, validate_schema

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("ORDER_VALIDATION_ENABLED", "1") == "1"
_MAX_DUPLICATE_CACHE = int(os.getenv("ORDER_DUPLICATE_CACHE_SIZE", "10000"))


class OrderValidator:
    """주문 데이터 검증기.

    사용 예:
        validator = OrderValidator()
        is_valid, errors = validator.validate_shopify(payload)
        if not is_valid:
            logger.error("주문 검증 실패: %s", errors)
    """

    def __init__(self):
        # 중복 주문 감지를 위한 order_id 캐시
        self._seen_ids: Set[str] = set()
        self._lock = threading.Lock()

    # ── 공개 API ──────────────────────────────────────────

    def validate_shopify(self, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Shopify 웹훅 페이로드를 검증한다.

        Args:
            payload: Shopify 주문 웹훅 JSON 딕셔너리

        Returns:
            (is_valid, errors): 유효 여부와 오류 메시지 목록
        """
        if not _ENABLED:
            return True, []

        errors: List[str] = []

        # 1) 스키마 검증
        schema_ok, schema_errors = validate_schema(payload, ORDER_SCHEMA)
        errors.extend(schema_errors)

        # 2) line_items 검증
        line_items_errors = self._validate_line_items(payload.get("line_items", []))
        errors.extend(line_items_errors)

        # 3) 금액 범위 검증
        price_errors = self._validate_price(payload.get("total_price"))
        errors.extend(price_errors)

        # 4) 중복 주문 감지
        order_id = payload.get("id")
        if order_id is not None:
            dup_error = self._check_duplicate(str(order_id))
            if dup_error:
                errors.append(dup_error)

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Shopify 주문 검증 실패 (order_id=%s): %s", payload.get("id"), errors)

        return is_valid, errors

    def validate_woocommerce(self, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """WooCommerce 웹훅 페이로드를 검증한다.

        Args:
            payload: WooCommerce 주문 웹훅 JSON 딕셔너리

        Returns:
            (is_valid, errors): 유효 여부와 오류 메시지 목록
        """
        if not _ENABLED:
            return True, []

        errors: List[str] = []

        # WooCommerce는 id 필드명이 동일
        order_id = payload.get("id")
        if not order_id:
            errors.append("필수 필드 누락: 'id'")
            return False, errors

        # line_items 필드명 확인 (WooCommerce: line_items)
        line_items = payload.get("line_items", [])
        if not isinstance(line_items, list):
            errors.append("타입 오류: 'line_items' — list 타입이어야 합니다")
        else:
            errors.extend(self._validate_line_items(line_items))

        # 총 금액
        total = payload.get("total")
        if total is not None:
            errors.extend(self._validate_price(str(total)))

        # 중복 주문 감지
        dup_error = self._check_duplicate(f"woo:{order_id}")
        if dup_error:
            errors.append(dup_error)

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("WooCommerce 주문 검증 실패 (order_id=%s): %s", order_id, errors)

        return is_valid, errors

    def reset_duplicate_cache(self):
        """중복 감지 캐시를 초기화한다."""
        with self._lock:
            self._seen_ids.clear()

    # ── 내부 검증 메서드 ──────────────────────────────────

    def _validate_line_items(self, line_items: List[Dict]) -> List[str]:
        """line_items 배열을 검증한다."""
        errors: List[str] = []
        if not line_items:
            errors.append("line_items가 비어 있습니다")
            return errors

        for i, item in enumerate(line_items):
            if not isinstance(item, dict):
                errors.append(f"line_items[{i}]: dict 타입이어야 합니다")
                continue
            qty = item.get("quantity")
            if qty is not None and (not isinstance(qty, int) or qty <= 0):
                errors.append(f"line_items[{i}].quantity 범위 오류: {qty} (1 이상이어야 합니다)")
        return errors

    def _validate_price(self, price_str: Optional[str]) -> List[str]:
        """가격 문자열을 파싱하고 범위를 검증한다."""
        if price_str is None:
            return []
        try:
            price = float(price_str)
            if price < 0:
                return [f"금액 범위 오류: {price_str} (음수 불허)"]
            if price > 100_000_000:
                return [f"금액 이상치 감지: {price_str} (1억 초과)"]
        except (ValueError, TypeError):
            return [f"금액 파싱 실패: '{price_str}'"]
        return []

    def _check_duplicate(self, order_id: str) -> Optional[str]:
        """중복 주문 여부를 확인하고 캐시에 등록한다."""
        with self._lock:
            if order_id in self._seen_ids:
                return f"중복 주문 감지: order_id={order_id}"
            # 캐시 크기 제한
            if len(self._seen_ids) >= _MAX_DUPLICATE_CACHE:
                # 가장 오래된 항목 일부 제거 (간단한 LRU 근사)
                to_remove = list(self._seen_ids)[:100]
                for k in to_remove:
                    self._seen_ids.discard(k)
            self._seen_ids.add(order_id)
        return None
