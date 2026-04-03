"""src/backup/restore_validator.py — 백업 복원 전 검증."""
from __future__ import annotations

from typing import Any, Dict, List


class RestoreValidator:
    """복원 전 백업 데이터 유효성 검증."""

    def validate(self, backup_data: dict, required_keys: List[str] | None = None) -> dict:
        """검증 결과 반환: {"valid": bool, "errors": list}."""
        errors: List[str] = []

        if not isinstance(backup_data, dict):
            errors.append("백업 데이터는 dict 타입이어야 합니다.")
            return {"valid": False, "errors": errors}

        for key in (required_keys or []):
            if key not in backup_data:
                errors.append(f"필수 키 누락: {key}")

        return {"valid": len(errors) == 0, "errors": errors}

    def validate_types(self, backup_data: dict, type_map: Dict[str, Any]) -> dict:
        """타입 검증."""
        errors: List[str] = []
        for key, expected_type in type_map.items():
            if key in backup_data and not isinstance(backup_data[key], expected_type):
                errors.append(
                    f"키 '{key}' 타입 오류: 예상={expected_type.__name__}, "
                    f"실제={type(backup_data[key]).__name__}"
                )
        return {"valid": len(errors) == 0, "errors": errors}
