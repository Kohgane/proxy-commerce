"""src/data_exchange/import_validator.py — 가져오기 유효성 검사."""
from __future__ import annotations


class ImportValidator:
    """가져오기 데이터 유효성 검사기."""

    def validate(self, data: list, schema: dict | None = None) -> dict:
        """데이터를 검사하고 결과를 반환한다."""
        valid: list = []
        invalid: list = []
        errors: list[str] = []

        for i, item in enumerate(data):
            item_errors: list[str] = []

            if schema:
                required = schema.get("required", [])
                types = schema.get("types", {})
                for field in required:
                    if not isinstance(item, dict) or field not in item:
                        item_errors.append(f"레코드 {i}: 필수 필드 없음: {field}")
                for field, expected_type in types.items():
                    if isinstance(item, dict) and field in item:
                        if not isinstance(item[field], expected_type):
                            item_errors.append(
                                f"레코드 {i}: {field} 타입 오류 (기대: {expected_type.__name__})"
                            )

            if item_errors:
                invalid.append(item)
                errors.extend(item_errors)
            else:
                valid.append(item)

        return {
            "valid": valid,
            "invalid": invalid,
            "errors": errors,
        }
