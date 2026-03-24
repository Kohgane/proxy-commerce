"""src/config/validator.py — 설정 유효성 검증.

필수 환경변수 존재 여부, 타입, 범위, 의존성 관계를 검증한다.
"""

import logging
import os
from typing import Any, List, Tuple

logger = logging.getLogger(__name__)

# 의존성 규칙: key가 존재하면 depends_on도 반드시 존재해야 함
_DEPENDENCY_RULES = [
    ("SHOPIFY_SHOP", "SHOPIFY_ACCESS_TOKEN"),
    ("SHOPIFY_SHOP", "SHOPIFY_CLIENT_SECRET"),
    ("WOO_BASE_URL", "WOO_CK"),
    ("WOO_BASE_URL", "WOO_CS"),
    ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
]

# 숫자 범위 규칙: (key, min, max)
_RANGE_RULES = [
    ("PORT", 1, 65535),
    ("TARGET_MARGIN_PCT", 0, 100),
    ("MIN_MARGIN_PCT", 0, 100),
    ("CONFIG_CHECK_INTERVAL", 1, 86400),
    ("LOW_STOCK_THRESHOLD", 0, 9999),
]


class ConfigValidator:
    """설정 유효성 검증기.

    사용 예:
        validator = ConfigValidator()
        is_valid, warnings, errors = validator.validate()
    """

    def validate(self) -> Tuple[bool, List[str], List[str]]:
        """전체 설정 유효성을 검증한다.

        Returns:
            (is_valid, warnings, errors) 튜플
            - is_valid: 오류가 없으면 True
            - warnings: 경고 메시지 목록
            - errors: 오류 메시지 목록
        """
        from .schema import get_all_config_schema

        warnings: List[str] = []
        errors: List[str] = []

        schema = get_all_config_schema()

        for entry in schema:
            name = entry["name"]
            value = os.environ.get(name)

            # 필수 필드 검증
            if entry.get("required") and not value:
                errors.append(f"필수 설정 누락: {name} — {entry.get('description', '')}")
                continue

            if value is None:
                continue

            # 타입 검증
            ok, msg = self.validate_field(name, value)
            if not ok:
                errors.append(msg)

        # 의존성 검증
        for key, depends_on in _DEPENDENCY_RULES:
            key_val = os.environ.get(key, "")
            dep_val = os.environ.get(depends_on, "")
            if key_val and not dep_val:
                warnings.append(
                    f"의존성 경고: {key} 설정 시 {depends_on}도 필요합니다."
                )

        is_valid = len(errors) == 0
        return is_valid, warnings, errors

    def validate_field(self, name: str, value: Any) -> Tuple[bool, str]:
        """단일 필드 유효성 검증.

        Args:
            name: 환경변수 이름
            value: 검증할 값

        Returns:
            (ok, message) 튜플
        """
        from .schema import get_schema_by_name

        schema = get_schema_by_name(name)
        if schema is None:
            return True, ""

        typ = schema.get("type", str)

        # 타입 변환 검증
        if typ in (int, float):
            try:
                converted = typ(value)
            except (ValueError, TypeError):
                return False, f"타입 오류: {name}={value!r} — {typ.__name__} 형식이 필요합니다."

            # 범위 검증
            for rule_key, min_val, max_val in _RANGE_RULES:
                if rule_key == name:
                    if not (min_val <= converted <= max_val):
                        return False, (
                            f"범위 오류: {name}={converted} — "
                            f"{min_val}~{max_val} 범위여야 합니다."
                        )

        return True, ""
