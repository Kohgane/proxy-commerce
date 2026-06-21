"""src/seller_console/word_rules.py — 금지어 필터 + 단어 치환 규칙 (Phase 248, v3 P1-5).

셀러별로 상품명/설명에서 ① 금지어(빼야 할 단어) ② 치환 규칙(A→B)을 설정하고,
등록·정제 시 적용한다. 퍼센티의 '금지어 필터 / 키워드·단어 치환'에 대응(실동작).

저장: GOOGLE_SHEET_ID 있으면 `word_rules` 워크시트(seller_id|banned|subs_json),
없으면 인메모리. (collect_history_store와 동일 패턴)
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_WS_NAME = "word_rules"
_HEADERS = ["seller_id", "banned", "subs_json"]

# 인메모리 폴백: seller_id → {"banned": [...], "subs": [{"from","to"}]}
_in_memory: dict[str, dict] = {}


def _get_worksheet():
    from src.utils.sheets import open_sheet
    ws = open_sheet(_SHEET_ID, _WS_NAME)
    try:
        first = ws.row_values(1)
        if not first or first[0] != "seller_id":
            ws.insert_row(_HEADERS, index=1)
    except Exception:
        pass
    return ws


def _parse_banned(raw) -> list[str]:
    if isinstance(raw, list):
        items = raw
    else:
        items = re.split(r"[\n,]", str(raw or ""))
    out, seen = [], set()
    for w in items:
        w = (w or "").strip()
        if w and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


def _parse_subs(raw) -> list[dict]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except (TypeError, ValueError):
            raw = []
    out = []
    for s in (raw or []):
        if isinstance(s, dict):
            frm = (s.get("from") or "").strip()
            to = (s.get("to") or "").strip()
            if frm:
                out.append({"from": frm, "to": to})
    return out


def get_rules(seller_id: Optional[str]) -> dict:
    """셀러의 규칙 {"banned": [...], "subs": [{"from","to"}]}."""
    sid = str(seller_id or "")
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            for row in ws.get_all_records():
                if str(row.get("seller_id", "") or "") == sid:
                    return {"banned": _parse_banned(row.get("banned")),
                            "subs": _parse_subs(row.get("subs_json"))}
            return {"banned": [], "subs": []}
        except Exception as exc:
            logger.warning("규칙 조회 실패(인메모리 폴백): %s", exc)
    r = _in_memory.get(sid) or {}
    return {"banned": list(r.get("banned", [])), "subs": list(r.get("subs", []))}


def save_rules(seller_id: Optional[str], banned, subs) -> dict:
    """규칙 저장(전체 교체). 정규화 후 반환."""
    sid = str(seller_id or "")
    norm = {"banned": _parse_banned(banned), "subs": _parse_subs(subs)}
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            values = ws.get_all_values()
            header = values[0] if values else _HEADERS
            col = {h: i for i, h in enumerate(header)}
            banned_str = "\n".join(norm["banned"])
            subs_str = json.dumps(norm["subs"], ensure_ascii=False)
            for r, row in enumerate(values[1:], start=2):
                if col.get("seller_id", 0) < len(row) and str(row[col["seller_id"]] or "") == sid:
                    ws.update_cell(r, col.get("banned", 1) + 1, banned_str)
                    ws.update_cell(r, col.get("subs_json", 2) + 1, subs_str)
                    return norm
            new_row = [""] * len(header)
            new_row[col.get("seller_id", 0)] = sid
            new_row[col.get("banned", 1)] = banned_str
            new_row[col.get("subs_json", 2)] = subs_str
            ws.append_row(new_row)
            return norm
        except Exception as exc:
            logger.warning("규칙 저장 실패(인메모리 폴백): %s", exc)
    _in_memory[sid] = norm
    return norm


def apply_rules(text: str, seller_id: Optional[str], rules: Optional[dict] = None) -> dict:
    """text에 치환→금지어 제거 순으로 적용.

    Returns: {"text": 정제본, "substituted": [{from,to}...], "removed": [금지어...], "changed": bool}
    """
    original = text or ""
    if rules is None:
        rules = get_rules(seller_id)
    out = original
    substituted = []
    for s in rules.get("subs", []):
        frm, to = s.get("from", ""), s.get("to", "")
        if frm and frm in out:
            out = out.replace(frm, to)
            substituted.append({"from": frm, "to": to})
    removed = []
    for w in rules.get("banned", []):
        if w and w in out:
            out = out.replace(w, "")
            removed.append(w)
    # 공백 정리
    out = re.sub(r"\s{2,}", " ", out).strip()
    return {"text": out, "substituted": substituted, "removed": removed, "changed": out != original}
