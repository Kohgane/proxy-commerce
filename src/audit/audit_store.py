"""src/audit/audit_store.py — Phase 41: 감사 로그 저장소 (인메모리 + 파일 백업)."""
import json
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


class AuditStore:
    """감사 로그 인메모리 저장소 + JSON Lines 파일 백업."""

    def __init__(self, max_records: int = 10000, backup_path: Optional[str] = None):
        self._records: List[dict] = []
        self.max_records = max_records
        self.backup_path = backup_path

    def append(self, entry: dict) -> dict:
        """감사 로그 추가."""
        self._records.append(entry)
        if len(self._records) > self.max_records:
            self._records = self._records[-self.max_records:]
        if self.backup_path:
            self._write_to_file(entry)
        return entry

    def get_all(self) -> List[dict]:
        """전체 레코드 반환."""
        return list(self._records)

    def get_recent(self, n: int = 100) -> List[dict]:
        """최근 N개 레코드 반환."""
        return self._records[-n:][::-1]

    def count(self) -> int:
        return len(self._records)

    def clear(self) -> int:
        """전체 삭제. 삭제된 수 반환."""
        count = len(self._records)
        self._records = []
        return count

    def _write_to_file(self, entry: dict) -> None:
        """JSON Lines 형식으로 파일 추가."""
        try:
            with open(self.backup_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as exc:
            logger.warning("감사 로그 파일 기록 실패: %s", exc)

    def load_from_file(self, path: Optional[str] = None) -> int:
        """파일에서 레코드 로드. 로드된 수 반환."""
        target = path or self.backup_path
        if not target or not os.path.exists(target):
            return 0
        loaded = 0
        try:
            with open(target, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._records.append(json.loads(line))
                        loaded += 1
        except Exception as exc:
            logger.warning("감사 로그 파일 로드 실패: %s", exc)
        return loaded
