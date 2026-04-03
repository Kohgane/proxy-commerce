"""src/feature_flags/flag_override.py — 플래그 오버라이드."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class FlagOverride:
    """특정 사용자/환경에 대한 플래그 오버라이드."""

    def __init__(self) -> None:
        # {(flag_name, user_id_or_env): {"value": bool, "created_at": str}}
        self._overrides: Dict[tuple, dict] = {}

    def set_user_override(self, flag_name: str, user_id: str,
                          value: bool) -> dict:
        key = ("user", flag_name, user_id)
        record = {
            "type": "user",
            "flag_name": flag_name,
            "user_id": user_id,
            "value": value,
            "created_at": _now_iso(),
        }
        self._overrides[key] = record
        return dict(record)

    def set_env_override(self, flag_name: str, environment: str,
                         value: bool) -> dict:
        key = ("env", flag_name, environment)
        record = {
            "type": "env",
            "flag_name": flag_name,
            "environment": environment,
            "value": value,
            "created_at": _now_iso(),
        }
        self._overrides[key] = record
        return dict(record)

    def get_user_override(self, flag_name: str, user_id: str) -> Optional[bool]:
        record = self._overrides.get(("user", flag_name, user_id))
        return record["value"] if record else None

    def get_env_override(self, flag_name: str, environment: str) -> Optional[bool]:
        record = self._overrides.get(("env", flag_name, environment))
        return record["value"] if record else None

    def remove_override(self, flag_name: str, user_id: str) -> None:
        self._overrides.pop(("user", flag_name, user_id), None)

    def list_overrides(self) -> List[dict]:
        return [dict(v) for v in self._overrides.values()]
