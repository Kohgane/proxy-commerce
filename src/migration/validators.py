"""src/migration/validators.py — Phase 42: 데이터 무결성 검증."""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DataValidator:
    """데이터 무결성 검증기.

    - 필수 필드 검사
    - 참조 무결성 검사
    - 타입 유효성 검사
    """

    def validate_required(self, data: dict, required_fields: List[str]) -> List[str]:
        """필수 필드 검사. 누락된 필드 목록 반환."""
        return [f for f in required_fields if not data.get(f)]

    def validate_type(self, value: Any, expected_type: type, field_name: str = '') -> Optional[str]:
        """타입 유효성 검사. 오류 메시지 반환 (없으면 None)."""
        if not isinstance(value, expected_type):
            return f"{field_name}: 타입 오류 (expected {expected_type.__name__}, got {type(value).__name__})"
        return None

    def validate_decimal(self, value: Any, field_name: str = '') -> Optional[str]:
        """Decimal 변환 가능 여부 검사."""
        try:
            Decimal(str(value))
            return None
        except (InvalidOperation, ValueError):
            return f"{field_name}: Decimal 변환 불가 ({value!r})"

    def validate_referential(
        self,
        data: dict,
        field: str,
        valid_ids: set,
        entity_name: str = '',
    ) -> Optional[str]:
        """참조 무결성 검사. 오류 메시지 반환 (없으면 None)."""
        ref_id = data.get(field)
        if ref_id and ref_id not in valid_ids:
            return f"{entity_name}.{field}: 참조 오류 ({ref_id!r} 없음)"
        return None

    def validate_product(self, product: dict) -> List[str]:
        """상품 데이터 유효성 검사."""
        errors = []
        errors.extend(self.validate_required(product, ['id', 'name', 'sku', 'price']))
        price_err = self.validate_decimal(product.get('price', 0), 'price')
        if price_err:
            errors.append(price_err)
        stock = product.get('stock')
        if stock is not None and not isinstance(stock, (int, float)):
            errors.append("stock: 숫자여야 합니다")
        return errors

    def validate_order(self, order: dict, valid_customer_ids: Optional[set] = None) -> List[str]:
        """주문 데이터 유효성 검사."""
        errors = []
        errors.extend(self.validate_required(order, ['id', 'customer_id', 'total_amount', 'status']))
        total_err = self.validate_decimal(order.get('total_amount', 0), 'total_amount')
        if total_err:
            errors.append(total_err)
        if valid_customer_ids:
            ref_err = self.validate_referential(order, 'customer_id', valid_customer_ids, 'order')
            if ref_err:
                errors.append(ref_err)
        return errors

    def validate_batch(self, records: List[dict], validator_fn) -> Dict[str, List[str]]:
        """배치 검증. record_id → errors 매핑 반환."""
        results = {}
        for record in records:
            record_id = record.get('id', str(records.index(record)))
            errors = validator_fn(record)
            if errors:
                results[record_id] = errors
        return results

    def is_valid(self, data: dict, required_fields: List[str]) -> bool:
        """간단한 유효성 여부 반환."""
        return len(self.validate_required(data, required_fields)) == 0
