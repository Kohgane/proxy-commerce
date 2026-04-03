"""src/integrations/google_sheets_connector.py — Google Sheets 연동 모의 구현."""
from __future__ import annotations

from typing import Dict, List

from .integration_connector import IntegrationConnector


class GoogleSheetsConnector(IntegrationConnector):
    """Google Sheets 연동 모의 구현 (실제 API 호출 없음)."""

    name = "google_sheets"

    def __init__(self, credentials: str = "mock-credentials") -> None:
        self.credentials = credentials
        self._connected = False
        self._sheets: Dict[str, List[list]] = {}

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def health_check(self) -> dict:
        return {"name": self.name, "status": "ok" if self._connected else "disconnected"}

    def read_sheet(self, sheet_id: str) -> List[list]:
        return self._sheets.get(sheet_id, [["id", "name", "price"], ["1", "상품1", "10000"]])

    def write_sheet(self, sheet_id: str, data: List[list]) -> dict:
        self._sheets[sheet_id] = data
        return {"sheet_id": sheet_id, "rows_written": len(data)}

    def sync(self) -> dict:
        return {"synced": True, "sheets": list(self._sheets.keys())}
