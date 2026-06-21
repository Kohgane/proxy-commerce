"""src/seller_console/pccc_store.py — 개인통관고유부호(PCCC) 입력·조회 (Phase 250, v3 P1-5).

구매대행은 통관 시 구매자의 개인통관고유부호(P + 12자리)가 필요하다. 셀러가 고객별
PCCC를 입력·검색·조회할 수 있게 한다(실제 저장, 셀러 격리).

저장: GOOGLE_SHEET_ID 있으면 `pccc` 워크시트, 없으면 인메모리.
※ 개인정보 — 셀러 본인 데이터만 접근(seller_id 격리). 마스킹은 화면단에서.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_WS_NAME = "pccc"
_HEADERS = ["id", "seller_id", "name", "phone", "pccc", "memo", "created_at"]

_in_memory: list[dict] = []

_PCCC_RE = re.compile(r"^[Pp]\d{12}$")


def normalize_pccc(code: str) -> str:
    return re.sub(r"\s|-", "", str(code or "")).upper()


def is_valid_pccc(code: str) -> bool:
    """한국 개인통관고유부호 형식(P + 12자리 숫자) 여부."""
    return bool(_PCCC_RE.match(normalize_pccc(code)))


def _get_worksheet():
    from src.utils.sheets import open_sheet
    ws = open_sheet(_SHEET_ID, _WS_NAME)
    try:
        first = ws.row_values(1)
        if not first or first[0] != "id":
            ws.insert_row(_HEADERS, index=1)
    except Exception:
        pass
    return ws


def add(seller_id: Optional[str], *, name: str, pccc: str, phone: str = "", memo: str = "") -> dict:
    sid = str(seller_id or "")
    rec = {
        "id": secrets.token_hex(5),
        "seller_id": sid,
        "name": (name or "").strip()[:60],
        "phone": (phone or "").strip()[:30],
        "pccc": normalize_pccc(pccc),
        "memo": (memo or "").strip()[:120],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            ws.append_row([rec[h] for h in _HEADERS])
            return rec
        except Exception as exc:
            logger.warning("PCCC 저장 실패(인메모리 폴백): %s", exc)
    _in_memory.append(rec)
    return rec


def list_records(seller_id: Optional[str], q: str = "") -> list[dict]:
    sid = str(seller_id or "")
    rows: list[dict] = []
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            rows = [r for r in ws.get_all_records() if str(r.get("seller_id", "") or "") == sid]
        except Exception as exc:
            logger.warning("PCCC 조회 실패(인메모리 폴백): %s", exc)
            rows = [dict(r) for r in _in_memory if str(r.get("seller_id", "") or "") == sid]
    else:
        rows = [dict(r) for r in _in_memory if str(r.get("seller_id", "") or "") == sid]
    ql = (q or "").strip().lower()
    if ql:
        rows = [r for r in rows
                if ql in str(r.get("name", "")).lower()
                or ql in str(r.get("phone", "")).lower()
                or ql in str(r.get("pccc", "")).lower()]
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rows


def delete(seller_id: Optional[str], rec_id: str) -> bool:
    sid = str(seller_id or "")
    rid = str(rec_id or "")
    if not rid:
        return False
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            values = ws.get_all_values()
            if values:
                header = values[0]
                idx = {h: i for i, h in enumerate(header)}
                id_i, sid_i = idx.get("id"), idx.get("seller_id")
                for r in range(len(values), 1, -1):
                    row = values[r - 1]
                    if id_i is not None and id_i < len(row) and row[id_i] == rid:
                        if sid_i is None or (sid_i < len(row) and str(row[sid_i] or "") == sid):
                            ws.delete_rows(r)
                            return True
            return False
        except Exception as exc:
            logger.warning("PCCC 삭제 실패(인메모리 폴백): %s", exc)
    before = len(_in_memory)
    _in_memory[:] = [r for r in _in_memory
                     if not (str(r.get("id")) == rid and str(r.get("seller_id", "") or "") == sid)]
    return len(_in_memory) < before
