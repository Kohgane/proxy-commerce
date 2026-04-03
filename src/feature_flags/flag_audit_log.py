"""src/feature_flags/flag_audit_log.py — 피쳐 플래그 감사 로그."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class FlagAuditLog:
    """피쳐 플래그 변경 감사 로그."""

    def __init__(self) -> None:
        self._log: List[dict] = []

    def record(
        self,
        flag_name: str,
        action: str,
        old_value,
        new_value,
        user_id: Optional[str] = None,
    ) -> None:
        self._log.append({
            "flag_name": flag_name,
            "action": action,
            "old_value": old_value,
            "new_value": new_value,
            "user_id": user_id,
            "recorded_at": _now_iso(),
        })

    def get_log(self, flag_name: Optional[str] = None) -> List[dict]:
        if flag_name:
            return [e for e in self._log if e["flag_name"] == flag_name]
        return list(self._log)

    def get_recent(self, limit: int = 20) -> List[dict]:
        return self._log[-limit:]
