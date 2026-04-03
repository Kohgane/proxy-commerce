"""src/backup/full_backup.py — 전체 백업 전략."""
from __future__ import annotations

import json

from .backup_strategy import BackupStrategy


class FullBackup(BackupStrategy):
    """전체 데이터를 JSON으로 직렬화."""

    def create(self, data: dict) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)

    def restore(self, backup_data: str) -> dict:
        return json.loads(backup_data)
