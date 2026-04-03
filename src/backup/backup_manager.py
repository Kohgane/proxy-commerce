"""src/backup/backup_manager.py — 백업 관리자."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .backup_strategy import BackupStrategy
from .full_backup import FullBackup


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class BackupManager:
    """백업 생성/복원/삭제/목록 관리 (인메모리)."""

    def __init__(self) -> None:
        self._backups: Dict[str, dict] = {}

    def create(self, data: dict, strategy: Optional[BackupStrategy] = None) -> dict:
        if strategy is None:
            strategy = FullBackup()
        backup_id = str(uuid.uuid4())
        serialized = strategy.create(data)
        entry = {
            "backup_id": backup_id,
            "strategy": type(strategy).__name__,
            "data": serialized,
            "created_at": _now_iso(),
            "size_bytes": len(serialized.encode()),
        }
        self._backups[backup_id] = entry
        return {k: v for k, v in entry.items() if k != "data"}

    def restore(self, backup_id: str, strategy: Optional[BackupStrategy] = None) -> dict:
        entry = self._backups.get(backup_id)
        if entry is None:
            raise KeyError(f"백업 없음: {backup_id}")
        if strategy is None:
            strategy = FullBackup()
        return strategy.restore(entry["data"])

    def delete(self, backup_id: str) -> None:
        if backup_id not in self._backups:
            raise KeyError(f"백업 없음: {backup_id}")
        del self._backups[backup_id]

    def list_backups(self) -> List[dict]:
        return [{k: v for k, v in b.items() if k != "data"} for b in self._backups.values()]

    def get(self, backup_id: str) -> Optional[dict]:
        entry = self._backups.get(backup_id)
        if entry is None:
            return None
        return {k: v for k, v in entry.items() if k != "data"}
