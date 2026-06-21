"""src/seller_console/translation_usage.py — 셀러별 번역 무료 사용량 미터 (Phase 246, v3 P1-4).

무료 번역 한도(기본 20회)를 셀러별로 '실제 카운트'로 관리한다(가짜 차감/가짜 무료 금지).
- 무료 잔여 = max(0, FREE_LIMIT - free_used)
- 초과 시: 활성 구독이면 허용, 아니면 토큰 차감 또는 차단(결제 미설정 시 정직 안내).

저장: GOOGLE_SHEET_ID 있으면 `translation_usage` 워크시트(seller_id|free_used),
없으면 인메모리. (collect_history_store와 동일 패턴)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_WS_NAME = "translation_usage"
_HEADERS = ["seller_id", "free_used"]

# 인메모리 폴백 (seller_id → free_used)
_in_memory: dict[str, int] = {}


def free_limit() -> int:
    try:
        return max(0, int(os.getenv("TRANSLATION_FREE_LIMIT", "20") or "20"))
    except (TypeError, ValueError):
        return 20


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


def get_used(seller_id: Optional[str]) -> int:
    """셀러의 무료 번역 사용 횟수."""
    sid = str(seller_id or "")
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            for row in ws.get_all_records():
                if str(row.get("seller_id", "") or "") == sid:
                    try:
                        return max(0, int(row.get("free_used", 0) or 0))
                    except (TypeError, ValueError):
                        return 0
            return 0
        except Exception as exc:
            logger.warning("번역 사용량 조회 실패(인메모리 폴백): %s", exc)
    return max(0, int(_in_memory.get(sid, 0)))


def remaining(seller_id: Optional[str]) -> int:
    """무료 잔여 횟수."""
    return max(0, free_limit() - get_used(seller_id))


def increment(seller_id: Optional[str], n: int) -> int:
    """무료 사용 n회 증가 후 새 누계 반환 (n<=0이면 변화 없음)."""
    sid = str(seller_id or "")
    n = int(n or 0)
    if n <= 0:
        return get_used(sid)

    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            values = ws.get_all_values()
            header = values[0] if values else _HEADERS
            col = {h: i for i, h in enumerate(header)}
            sid_i = col.get("seller_id", 0)
            used_i = col.get("free_used", 1)
            for r, row in enumerate(values[1:], start=2):
                if sid_i < len(row) and str(row[sid_i] or "") == sid:
                    cur = 0
                    try:
                        cur = int(row[used_i]) if used_i < len(row) and row[used_i] else 0
                    except (TypeError, ValueError):
                        cur = 0
                    new_total = cur + n
                    ws.update_cell(r, used_i + 1, str(new_total))
                    return new_total
            # 신규 셀러 행 추가
            new_total = n
            new_row = [""] * len(header)
            new_row[sid_i] = sid
            new_row[used_i] = str(new_total)
            ws.append_row(new_row)
            return new_total
        except Exception as exc:
            logger.warning("번역 사용량 증가 실패(인메모리 폴백): %s", exc)

    _in_memory[sid] = max(0, int(_in_memory.get(sid, 0))) + n
    return _in_memory[sid]
