"""src/validation/schemas.py — 공통 스키마 정의.

주문, 상품, 환율 데이터의 dict 기반 간단한 스키마 검증 (외부 라이브러리 미사용).

스키마 형식:
    {
        "field_name": {
            "type": type,           # 필수: 타입 (str, int, float, dict, list 등)
            "required": bool,       # 필수 여부 (기본 True)
            "min": number,          # 최소값 (숫자형에만 적용)
            "max": number,          # 최대값 (숫자형에만 적용)
            "choices": list,        # 허용값 목록
            "nullable": bool,       # None 허용 여부 (기본 False)
        }
    }
"""

from typing import Any, Dict, List, Tuple

# ──────────────────────────────────────────────────────────
# 스키마 검증 함수
# ──────────────────────────────────────────────────────────


def validate_schema(data: Dict[str, Any], schema: Dict[str, Dict]) -> Tuple[bool, List[str]]:
    """데이터가 스키마를 만족하는지 검증한다.

    Args:
        data: 검증할 딕셔너리
        schema: 스키마 정의 딕셔너리

    Returns:
        (is_valid, errors): 유효 여부와 오류 메시지 목록
    """
    errors: List[str] = []

    for field, rules in schema.items():
        required = rules.get("required", True)
        nullable = rules.get("nullable", False)
        expected_type = rules.get("type")

        value = data.get(field)

        # 필수 필드 존재 여부
        if value is None:
            if nullable:
                continue
            if required:
                errors.append(f"필수 필드 누락: '{field}'")
            continue

        # 타입 검사
        if expected_type and not isinstance(value, expected_type):
            errors.append(
                f"타입 오류: '{field}' — 예상={expected_type.__name__}, 실제={type(value).__name__}"
            )
            continue

        # 범위 검사 (숫자형)
        if isinstance(value, (int, float)):
            min_val = rules.get("min")
            max_val = rules.get("max")
            if min_val is not None and value < min_val:
                errors.append(f"범위 오류: '{field}' 값 {value} < 최소값 {min_val}")
            if max_val is not None and value > max_val:
                errors.append(f"범위 오류: '{field}' 값 {value} > 최대값 {max_val}")

        # 허용값 검사
        choices = rules.get("choices")
        if choices is not None and value not in choices:
            errors.append(f"허용값 오류: '{field}' 값 '{value}' — 허용={choices}")

        # 문자열 최소 길이
        if isinstance(value, str):
            min_len = rules.get("min_length")
            if min_len is not None and len(value) < min_len:
                errors.append(f"길이 오류: '{field}' 길이 {len(value)} < 최소 {min_len}")

    return len(errors) == 0, errors


# ──────────────────────────────────────────────────────────
# 주문 스키마 (Shopify webhook 기준)
# ──────────────────────────────────────────────────────────

ORDER_SCHEMA: Dict[str, Dict] = {
    "id": {"type": int, "required": True, "min": 1},
    "order_number": {"type": int, "required": False},
    "email": {"type": str, "required": False, "nullable": True},
    "total_price": {"type": str, "required": False, "nullable": True},
    "currency": {"type": str, "required": False, "nullable": True},
    "financial_status": {
        "type": str,
        "required": False,
        "nullable": True,
        "choices": ["pending", "authorized", "partially_paid", "paid", "partially_refunded", "refunded", "voided"],
    },
    "line_items": {"type": list, "required": True},
}

# ──────────────────────────────────────────────────────────
# 상품 스키마 (카탈로그 동기화 기준)
# ──────────────────────────────────────────────────────────

PRODUCT_SCHEMA: Dict[str, Dict] = {
    "sku": {"type": str, "required": True, "min_length": 3},
    "title": {"type": str, "required": True, "min_length": 1},
    "price_krw": {"type": (int, float), "required": True, "min": 0},
    "stock": {"type": int, "required": False, "min": 0},
    "vendor": {"type": str, "required": False, "nullable": True},
    "category": {"type": str, "required": False, "nullable": True},
}

# ──────────────────────────────────────────────────────────
# 환율 스키마
# ──────────────────────────────────────────────────────────

FX_SCHEMA: Dict[str, Dict] = {
    "base": {"type": str, "required": True, "min_length": 3},
    "target": {"type": str, "required": True, "min_length": 3},
    "rate": {"type": (int, float), "required": True, "min": 0.000001},
    "timestamp": {"type": str, "required": False, "nullable": True},
}
