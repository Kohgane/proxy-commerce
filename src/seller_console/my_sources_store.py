"""src/seller_console/my_sources_store.py — My Sources 즐겨찾기 저장소 (Phase 160).

셀러가 자주 수집하는 사이트/도메인을 저장·조회·삭제한다.
영속화: GOOGLE_SHEET_ID 설정 시 Sheets 'my_sources' 워크시트, 아니면 인메모리 fallback.

스키마 (각 행):
    domain    | label    | url_example            | added_at
    --------- | -------- | ---------------------- | --------
    brand.com | 브랜드몰  | https://brand.com/shop | 2026-06-01T00:00:00Z
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
_WORKSHEET_NAME = "my_sources"


@dataclass
class SourceEntry:
    """즐겨찾기 소스 항목."""
    domain: str
    label: str = ""
    url_example: str = ""
    added_at: str = ""

    def __post_init__(self) -> None:
        if not self.added_at:
            self.added_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not self.label:
            self.label = self.domain

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_row(row: dict) -> "SourceEntry":
        return SourceEntry(
            domain=row.get("domain", ""),
            label=row.get("label", ""),
            url_example=row.get("url_example", ""),
            added_at=row.get("added_at", ""),
        )


# ---------------------------------------------------------------------------
# 인메모리 fallback 저장소
# ---------------------------------------------------------------------------
_MEM_STORE: List[SourceEntry] = []


class MySourcesStore:
    """My Sources CRUD."""

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def list(self) -> List[SourceEntry]:
        """저장된 모든 소스 반환."""
        if _SHEET_ID:
            try:
                return self._sheet_list()
            except Exception as exc:
                logger.warning("my_sources 시트 조회 실패 → 인메모리: %s", exc)
        return list(_MEM_STORE)

    def add(self, domain: str, label: str = "", url_example: str = "") -> SourceEntry:
        """새 소스 추가 (중복 도메인 무시)."""
        domain = _normalize_domain(domain)
        if not domain:
            raise ValueError("domain이 비어있습니다.")

        existing = self.list()
        for e in existing:
            if e.domain == domain:
                return e  # 이미 존재

        entry = SourceEntry(domain=domain, label=label or domain, url_example=url_example)
        if _SHEET_ID:
            try:
                self._sheet_add(entry)
                return entry
            except Exception as exc:
                logger.warning("my_sources 시트 추가 실패 → 인메모리: %s", exc)
        _MEM_STORE.append(entry)
        return entry

    def remove(self, domain: str) -> bool:
        """도메인 삭제. 성공 시 True."""
        domain = _normalize_domain(domain)
        if _SHEET_ID:
            try:
                return self._sheet_remove(domain)
            except Exception as exc:
                logger.warning("my_sources 시트 삭제 실패 → 인메모리: %s", exc)
        global _MEM_STORE
        before = len(_MEM_STORE)
        _MEM_STORE = [e for e in _MEM_STORE if e.domain != domain]
        return len(_MEM_STORE) < before

    # ------------------------------------------------------------------
    # Sheets 구현
    # ------------------------------------------------------------------

    def _get_worksheet(self):
        """gspread 워크시트 반환. 없으면 생성."""
        import gspread
        from google.oauth2.service_account import Credentials

        creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not creds_json:
            raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON 미설정")
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(_SHEET_ID)
        try:
            ws = sh.worksheet(_WORKSHEET_NAME)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(_WORKSHEET_NAME, rows=500, cols=4)
            ws.append_row(["domain", "label", "url_example", "added_at"])
        return ws

    def _sheet_list(self) -> List[SourceEntry]:
        ws = self._get_worksheet()
        records = ws.get_all_records()
        return [SourceEntry.from_row(r) for r in records if r.get("domain")]

    def _sheet_add(self, entry: SourceEntry) -> None:
        ws = self._get_worksheet()
        ws.append_row([entry.domain, entry.label, entry.url_example, entry.added_at])

    def _sheet_remove(self, domain: str) -> bool:
        ws = self._get_worksheet()
        cell = ws.find(domain)
        if cell is None:
            return False
        ws.delete_rows(cell.row)
        return True


def _normalize_domain(raw: str) -> str:
    """URL 또는 도메인 문자열 → 정규화된 도메인."""
    raw = raw.strip().lower()
    if raw.startswith(("http://", "https://")):
        from urllib.parse import urlparse
        parsed = urlparse(raw)
        raw = parsed.netloc or raw
    # www. 제거
    if raw.startswith("www."):
        raw = raw[4:]
    return raw
