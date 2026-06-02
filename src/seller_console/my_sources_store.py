"""src/seller_console/my_sources_store.py — My Sources 저장소 (Phase 160)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_WS_NAME = "my_sources"
_HEADERS = ["domain", "label", "note", "created_at", "last_used_at"]
_in_memory: dict[str, dict] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_domain(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.netloc or parsed.path or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host if "." in host else ""


def _sheet():
    if not _SHEET_ID:
        return None
    try:
        from src.utils.sheets import open_sheet
        ws = open_sheet(_SHEET_ID, _WS_NAME)
        first = ws.row_values(1)
        if not first or first[0] != "domain":
            ws.insert_row(_HEADERS, index=1)
        return ws
    except Exception as exc:
        logger.debug("My Sources 워크시트 접근 실패: %s", exc)
        return None


def list_sources() -> list[dict]:
    rows: list[dict] = []
    ws = _sheet()
    if ws is not None:
        try:
            rows = [r for r in ws.get_all_records() if (r.get("domain") or "").strip()]
        except Exception as exc:
            logger.debug("My Sources 목록 조회 실패: %s", exc)
            rows = []
    if not rows:
        rows = list(_in_memory.values())
    rows = [dict(r) for r in rows]
    rows.sort(key=lambda r: (r.get("last_used_at") or r.get("created_at") or ""), reverse=True)
    return rows


def add_source(value: str, label: str = "", note: str = "") -> dict:
    domain = normalize_domain(value)
    if not domain:
        raise ValueError("도메인 형식이 올바르지 않습니다.")
    now = _utc_now()
    entry = {
        "domain": domain,
        "label": (label or domain).strip()[:120],
        "note": (note or "").strip()[:300],
        "created_at": now,
        "last_used_at": now,
    }
    _in_memory[domain] = entry

    ws = _sheet()
    if ws is not None:
        try:
            records = ws.get_all_records()
            for idx, row in enumerate(records, start=2):
                if normalize_domain(row.get("domain", "")) == domain:
                    ws.update_cell(idx, 2, entry["label"])
                    ws.update_cell(idx, 3, entry["note"])
                    ws.update_cell(idx, 5, entry["last_used_at"])
                    return entry
            ws.append_row([entry[h] for h in _HEADERS])
        except Exception as exc:
            logger.debug("My Sources 저장 실패 (sheet): %s", exc)
    return entry


def touch_source(value: str) -> bool:
    domain = normalize_domain(value)
    if not domain:
        return False
    entry = _in_memory.get(domain)
    now = _utc_now()
    if entry:
        entry["last_used_at"] = now

    ws = _sheet()
    if ws is not None:
        try:
            records = ws.get_all_records()
            for idx, row in enumerate(records, start=2):
                if normalize_domain(row.get("domain", "")) == domain:
                    ws.update_cell(idx, 5, now)
                    return True
        except Exception as exc:
            logger.debug("My Sources touch 실패 (sheet): %s", exc)
    return domain in _in_memory


def remove_source(value: str) -> bool:
    domain = normalize_domain(value)
    if not domain:
        return False
    removed = _in_memory.pop(domain, None) is not None

    ws = _sheet()
    if ws is not None:
        try:
            records = ws.get_all_records()
            for idx, row in enumerate(records, start=2):
                if normalize_domain(row.get("domain", "")) == domain:
                    ws.delete_rows(idx)
                    return True
        except Exception as exc:
            logger.debug("My Sources 삭제 실패 (sheet): %s", exc)
    return removed
