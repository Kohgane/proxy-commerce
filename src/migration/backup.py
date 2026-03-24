"""
데이터 백업 — 마이그레이션 전 Google Sheets 전체 워크시트 스냅샷.
"""

import csv
import io
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_BACKUP_ENABLED_DEFAULT = int(os.getenv("MIGRATION_BACKUP_ENABLED", "1"))


class BackupManager:
    """마이그레이션 전 데이터 백업 관리자.

    Google Sheets의 모든 워크시트를 CSV 문자열로 메모리에 저장하고
    필요 시 복원할 수 있다.
    """

    def __init__(self, sheets_client=None, sheet_id: Optional[str] = None):
        """초기화.

        인자:
            sheets_client: gspread 클라이언트
            sheet_id: Google Sheets 스프레드시트 ID
        """
        self._client = sheets_client
        self._sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID", "")
        self._backups: List[dict] = []  # 백업 이력

    # ── 백업 생성 ─────────────────────────────────────────────

    def create_backup(self, label: str = "") -> Optional[dict]:
        """현재 스프레드시트 전체를 백업한다.

        인자:
            label: 백업 레이블 (예: "before_v002_migration")

        반환:
            백업 메타데이터 딕셔너리 또는 실패 시 None
        """
        if not _BACKUP_ENABLED_DEFAULT:
            logger.info("MIGRATION_BACKUP_ENABLED=0 — 백업 건너뜀")
            return None

        if self._client is None:
            logger.warning("sheets_client 없음 — 백업 불가")
            return None

        import datetime
        try:
            spreadsheet = self._client.open_by_key(self._sheet_id)
            snapshots: Dict[str, str] = {}

            for ws in spreadsheet.worksheets():
                rows = ws.get_all_values()
                snapshots[ws.title] = self._rows_to_csv(rows)
                logger.debug("워크시트 백업: %s (%d행)", ws.title, len(rows))

            backup = {
                "label": label,
                "created_at": datetime.datetime.utcnow().isoformat(),
                "sheet_id": self._sheet_id,
                "worksheets": list(snapshots.keys()),
                "snapshots": snapshots,
            }
            self._backups.append(backup)
            logger.info("백업 완료: label=%r, 워크시트 수=%d", label, len(snapshots))
            return backup
        except Exception as exc:  # noqa: BLE001
            logger.error("백업 실패: %s", exc)
            return None

    # ── 백업 조회 ─────────────────────────────────────────────

    def list_backups(self) -> List[dict]:
        """백업 이력 목록을 반환한다 (스냅샷 데이터 제외)."""
        return [
            {k: v for k, v in b.items() if k != "snapshots"}
            for b in self._backups
        ]

    def get_latest_backup(self) -> Optional[dict]:
        """가장 최근 백업을 반환한다."""
        return self._backups[-1] if self._backups else None

    # ── CSV 변환 ──────────────────────────────────────────────

    @staticmethod
    def _rows_to_csv(rows: List[List[str]]) -> str:
        """행 목록을 CSV 문자열로 변환한다."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return output.getvalue()

    @staticmethod
    def csv_to_rows(csv_str: str) -> List[List[str]]:
        """CSV 문자열을 행 목록으로 변환한다."""
        reader = csv.reader(io.StringIO(csv_str))
        return list(reader)
