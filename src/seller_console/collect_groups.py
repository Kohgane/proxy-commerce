"""src/seller_console/collect_groups.py — 수집 상품 그룹 (Phase 247, v3 P1-5 퍼센티 그룹관리).

셀러별 상품 그룹 CRUD. 상품은 extra_json.group_id 로 그룹에 배정되며, 그룹 단위로
수집 이력 필터·일괄작업을 할 수 있다(가짜 그룹 금지 — 실제 저장).

저장: GOOGLE_SHEET_ID 있으면 `collect_groups` 워크시트(id|seller_id|name|created_at),
없으면 인메모리. (collect_history_store와 동일 패턴)
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_WS_NAME = "collect_groups"
_HEADERS = ["id", "seller_id", "name", "created_at"]

# 인메모리 폴백: list of dict
_in_memory: list[dict] = []


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


def list_groups(seller_id: Optional[str]) -> list[dict]:
    """셀러의 그룹 목록 (최신순)."""
    sid = str(seller_id or "")
    rows: list[dict] = []
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            rows = [r for r in ws.get_all_records() if str(r.get("seller_id", "") or "") == sid]
        except Exception as exc:
            logger.warning("그룹 목록 조회 실패(인메모리 폴백): %s", exc)
            rows = [dict(r) for r in _in_memory if str(r.get("seller_id", "") or "") == sid]
    else:
        rows = [dict(r) for r in _in_memory if str(r.get("seller_id", "") or "") == sid]
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return [{"id": r.get("id"), "name": r.get("name", "")} for r in rows]


def create_group(seller_id: Optional[str], name: str) -> Optional[dict]:
    """그룹 생성. 같은 이름이 있으면 그걸 반환(중복 생성 방지)."""
    sid = str(seller_id or "")
    name = (name or "").strip()[:60]
    if not name:
        return None
    for g in list_groups(sid):
        if g["name"] == name:
            return g
    gid = secrets.token_hex(4)
    row = {"id": gid, "seller_id": sid, "name": name,
           "created_at": datetime.now(timezone.utc).isoformat()}
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            ws.append_row([row[h] for h in _HEADERS])
        except Exception as exc:
            logger.warning("그룹 생성 Sheets 실패(인메모리 폴백): %s", exc)
            _in_memory.append(row)
    else:
        _in_memory.append(row)
    return {"id": gid, "name": name}


def delete_group(seller_id: Optional[str], group_id: str) -> bool:
    """그룹 삭제(상품의 group_id는 그대로 — 그룹만 사라짐). 셀러 격리."""
    sid = str(seller_id or "")
    gid = str(group_id or "")
    if not gid:
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
                    if id_i is not None and id_i < len(row) and row[id_i] == gid:
                        if sid_i is None or (sid_i < len(row) and str(row[sid_i] or "") == sid):
                            ws.delete_rows(r)
                            return True
            return False
        except Exception as exc:
            logger.warning("그룹 삭제 Sheets 실패(인메모리 폴백): %s", exc)
    before = len(_in_memory)
    _in_memory[:] = [r for r in _in_memory
                     if not (str(r.get("id")) == gid and str(r.get("seller_id", "") or "") == sid)]
    return len(_in_memory) < before
