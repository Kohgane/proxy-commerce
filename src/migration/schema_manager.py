"""
스키마 버전 관리 — Google Sheets 'schema_version' 워크시트 기반.

현재 스키마 버전을 조회하고 업데이트하는 기능을 제공한다.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 기본 환경변수
_DEFAULT_WORKSHEET = os.getenv("SCHEMA_VERSION_WORKSHEET", "schema_version")


class SchemaManager:
    """Google Sheets 스키마 버전 관리자.

    스프레드시트의 'schema_version' 워크시트에서 현재 버전을 읽고 쓴다.
    워크시트 구조: A1=version, B1=updated_at, C1=description
    """

    CURRENT_SCHEMA_VERSION = "001"  # 코드베이스 기준 최신 버전

    def __init__(self, sheets_client=None, sheet_id: Optional[str] = None):
        """초기화.

        인자:
            sheets_client: gspread 클라이언트 또는 None (테스트용)
            sheet_id: Google Sheets 스프레드시트 ID
        """
        self._client = sheets_client
        self._sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID", "")
        self._worksheet_name = _DEFAULT_WORKSHEET

    # ── 버전 조회 ─────────────────────────────────────────────

    def get_current_version(self) -> Optional[str]:
        """스프레드시트에서 현재 스키마 버전을 가져온다.

        반환:
            버전 문자열 (예: "001") 또는 버전 정보 없으면 None
        """
        if self._client is None:
            logger.warning("sheets_client 가 없습니다 — 버전 조회 불가")
            return None

        try:
            spreadsheet = self._client.open_by_key(self._sheet_id)
            try:
                ws = spreadsheet.worksheet(self._worksheet_name)
            except Exception:  # noqa: BLE001
                logger.info("'%s' 워크시트 없음 — 마이그레이션 필요", self._worksheet_name)
                return None

            value = ws.cell(1, 1).value
            return str(value).strip() if value else None
        except Exception as exc:  # noqa: BLE001
            logger.error("스키마 버전 조회 실패: %s", exc)
            return None

    def needs_migration(self) -> bool:
        """마이그레이션이 필요한지 확인한다.

        현재 스프레드시트 버전이 코드베이스 버전보다 낮으면 True.

        반환:
            마이그레이션 필요 여부
        """
        current = self.get_current_version()
        if current is None:
            return True  # 버전 정보 없으면 마이그레이션 필요
        return current < self.CURRENT_SCHEMA_VERSION

    def update_version(self, version: str, description: str = "") -> bool:
        """스프레드시트의 스키마 버전을 업데이트한다.

        인자:
            version: 새 버전 문자열
            description: 버전 설명

        반환:
            성공 여부
        """
        if self._client is None:
            logger.warning("sheets_client 가 없습니다 — 버전 업데이트 불가")
            return False

        import datetime

        try:
            spreadsheet = self._client.open_by_key(self._sheet_id)
            # 워크시트 없으면 생성
            try:
                ws = spreadsheet.worksheet(self._worksheet_name)
            except Exception:  # noqa: BLE001
                ws = spreadsheet.add_worksheet(self._worksheet_name, rows=10, cols=5)
                ws.update("A1:C1", [["version", "updated_at", "description"]])

            now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            ws.update("A2:C2", [[version, now, description]])
            logger.info("스키마 버전 업데이트: %s", version)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("스키마 버전 업데이트 실패: %s", exc)
            return False

    def ensure_worksheet(self) -> bool:
        """schema_version 워크시트가 없으면 생성한다.

        반환:
            성공 여부
        """
        if self._client is None:
            return False

        try:
            spreadsheet = self._client.open_by_key(self._sheet_id)
            try:
                spreadsheet.worksheet(self._worksheet_name)
                return True  # 이미 존재
            except Exception:  # noqa: BLE001
                ws = spreadsheet.add_worksheet(self._worksheet_name, rows=10, cols=5)
                ws.update("A1:C1", [["version", "updated_at", "description"]])
                logger.info("'%s' 워크시트 생성 완료", self._worksheet_name)
                return True
        except Exception as exc:  # noqa: BLE001
            logger.error("워크시트 생성 실패: %s", exc)
            return False
