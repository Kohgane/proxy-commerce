"""src/form_builder/form_validator.py — 폼 제출 데이터 검증."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .form_definition import FormDefinition, FormField, FieldType


class FormValidator:
    """폼 제출 데이터 검증."""

    def validate(self, form: FormDefinition, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """폼 정의에 따라 데이터 검증.

        Returns:
            (is_valid, errors)
        """
        errors: List[str] = []
        for field in form.fields:
            value = data.get(field.name)
            # 필수 검사
            if field.required and (value is None or value == ""):
                errors.append(f"{field.label}({field.name})은(는) 필수 항목입니다")
                continue
            if value is None or value == "":
                continue
            # 타입별 검증
            field_errors = self._validate_field(field, value)
            errors.extend(field_errors)
        # 폼 수준 커스텀 규칙
        for rule_name, rule_conf in form.validation_rules.items():
            rule_errors = self._apply_custom_rule(rule_name, rule_conf, data)
            errors.extend(rule_errors)
        return len(errors) == 0, errors

    def _validate_field(self, field: FormField, value: Any) -> List[str]:
        errors: List[str] = []
        ft = field.field_type
        v = field.validation

        if ft == FieldType.NUMBER:
            try:
                num = float(value)
                if "min" in v and num < float(v["min"]):
                    errors.append(f"{field.label}: 최솟값은 {v['min']}입니다")
                if "max" in v and num > float(v["max"]):
                    errors.append(f"{field.label}: 최댓값은 {v['max']}입니다")
            except (TypeError, ValueError):
                errors.append(f"{field.label}: 숫자 값이 필요합니다")

        elif ft in (FieldType.TEXT, FieldType.TEXTAREA, FieldType.EMAIL, FieldType.PHONE):
            str_val = str(value)
            if "min_length" in v and len(str_val) < int(v["min_length"]):
                errors.append(f"{field.label}: 최소 {v['min_length']}자 이상이어야 합니다")
            if "max_length" in v and len(str_val) > int(v["max_length"]):
                errors.append(f"{field.label}: 최대 {v['max_length']}자 이하여야 합니다")
            if "pattern" in v:
                if not re.match(v["pattern"], str_val):
                    errors.append(f"{field.label}: 형식이 올바르지 않습니다")
            if ft == FieldType.EMAIL:
                if not re.match(r"^[^@]+@[^@]+\.[^@]+$", str_val):
                    errors.append(f"{field.label}: 유효한 이메일 주소가 아닙니다")

        elif ft == FieldType.SELECT:
            if field.options and value not in field.options:
                errors.append(f"{field.label}: 허용된 옵션이 아닙니다 ({field.options})")

        return errors

    def _apply_custom_rule(self, rule_name: str, rule_conf: dict,
                            data: Dict[str, Any]) -> List[str]:
        """커스텀 규칙 적용."""
        errors: List[str] = []
        rule_type = rule_conf.get("type")
        if rule_type == "fields_match":
            fields = rule_conf.get("fields", [])
            if len(fields) >= 2:
                values = [data.get(f) for f in fields]
                if len(set(str(v) for v in values)) > 1:
                    errors.append(rule_conf.get("message", f"{rule_name}: 필드 값이 일치하지 않습니다"))
        return errors
