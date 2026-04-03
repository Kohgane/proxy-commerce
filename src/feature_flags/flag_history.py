"""src/feature_flags/flag_history.py — 플래그 변경 이력 추적."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class FlagHistoryEntry:
    """플래그 변경 이력 항목."""
    flag_name: str
    action: str         # created, updated, deleted, toggled
    changed_by: str = "system"
    changes: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "flag_name": self.flag_name,
            "action": self.action,
            "changed_by": self.changed_by,
            "changes": self.changes,
            "timestamp": self.timestamp,
        }


class FlagHistory:
    """피처 플래그 변경 이력 관리."""

    def __init__(self) -> None:
        self._entries: List[FlagHistoryEntry] = []

    def record(self, flag_name: str, action: str,
               changed_by: str = "system", changes: dict = None) -> FlagHistoryEntry:
        entry = FlagHistoryEntry(
            flag_name=flag_name,
            action=action,
            changed_by=changed_by,
            changes=changes or {},
        )
        self._entries.append(entry)
        return entry

    def get_flag_history(self, flag_name: str) -> List[dict]:
        return [e.to_dict() for e in self._entries if e.flag_name == flag_name]

    def get_all(self) -> List[dict]:
        return [e.to_dict() for e in self._entries]
