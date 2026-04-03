"""src/backup/incremental_backup.py — 증분 백업 전략."""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class IncrementalBackup:
    """변경된 키만 저장하는 증분 백업."""

    def __init__(self) -> None:
        self._last_snapshot: dict = {}
        self._last_timestamp: str = ""

    def create(self, data: dict) -> str:
        changed = {k: v for k, v in data.items() if self._last_snapshot.get(k) != v}
        deleted = [k for k in self._last_snapshot if k not in data]
        snapshot = {
            "changed": changed,
            "deleted": deleted,
            "timestamp": _now_iso(),
            "base_timestamp": self._last_timestamp,
        }
        self._last_snapshot = dict(data)
        self._last_timestamp = snapshot["timestamp"]
        return json.dumps(snapshot, ensure_ascii=False, default=str)

    def restore(self, backup_data: str) -> dict:
        snapshot = json.loads(backup_data)
        result = dict(self._last_snapshot)
        result.update(snapshot.get("changed", {}))
        for k in snapshot.get("deleted", []):
            result.pop(k, None)
        return result
