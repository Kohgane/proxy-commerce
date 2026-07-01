"""src/seller_console/billing_store.py — 셀러 요금제/토큰 잔액 (Phase 258, v6 쉽고 간편 결제).

셀러별 plan(free/plus/pro) + token_balance를 저장한다. 유료 활성은 실제 결제 확인 시에만
(가짜 활성 금지 — 결제 미설정 시 free 유지 + 정직 안내).

저장: GOOGLE_SHEET_ID 있으면 `billing` 워크시트, 없으면 인메모리.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_WS_NAME = "billing"
_HEADERS = ["seller_id", "plan", "token_balance"]

_in_memory: dict[str, dict] = {}
_pending_payments: dict[str, dict] = {}

PLANS = {
    "free": {"label": "Free", "price_krw": 0, "translate_unlimited": False,
             "desc": "기본 수집·편집·등록. 무료 번역 20회."},
    "plus": {"label": "Plus", "price_krw": 19000, "translate_unlimited": True,
             "desc": "번역 무제한 · 대량 수집 · 자동 등록."},
    "pro": {"label": "Pro", "price_krw": 49000, "translate_unlimited": True,
            "desc": "Plus + 소싱 모니터링 · 우선 지원."},
}


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


def get_account(seller_id: Optional[str]) -> dict:
    """셀러 결제 상태 {plan, token_balance}."""
    sid = str(seller_id or "")
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            for row in ws.get_all_records():
                if str(row.get("seller_id", "") or "") == sid:
                    plan = str(row.get("plan", "free") or "free")
                    try:
                        bal = int(row.get("token_balance", 0) or 0)
                    except (TypeError, ValueError):
                        bal = 0
                    return {"plan": plan if plan in PLANS else "free", "token_balance": max(0, bal)}
            return {"plan": "free", "token_balance": 0}
        except Exception as exc:
            logger.warning("billing 조회 실패(인메모리 폴백): %s", exc)
    acc = _in_memory.get(sid) or {}
    return {"plan": acc.get("plan", "free"), "token_balance": max(0, int(acc.get("token_balance", 0)))}


def is_unlimited(seller_id: Optional[str]) -> bool:
    """현재 플랜이 번역 무제한인지."""
    plan = get_account(seller_id).get("plan", "free")
    return bool(PLANS.get(plan, {}).get("translate_unlimited"))


def set_plan(seller_id: Optional[str], plan: str) -> dict:
    """플랜 설정(실제 결제 확인 후/무료). 잘못된 plan은 free."""
    sid = str(seller_id or "")
    plan = plan if plan in PLANS else "free"
    cur = get_account(sid)
    cur["plan"] = plan
    _save(sid, cur)
    return cur


def add_tokens(seller_id: Optional[str], amount: int) -> dict:
    sid = str(seller_id or "")
    cur = get_account(sid)
    cur["token_balance"] = max(0, cur["token_balance"] + int(amount or 0))
    _save(sid, cur)
    return cur


def _save(sid: str, acc: dict) -> None:
    if _SHEET_ID:
        try:
            ws = _get_worksheet()
            values = ws.get_all_values()
            header = values[0] if values else _HEADERS
            col = {h: i for i, h in enumerate(header)}
            for r, row in enumerate(values[1:], start=2):
                if col.get("seller_id", 0) < len(row) and str(row[col["seller_id"]] or "") == sid:
                    ws.update_cell(r, col.get("plan", 1) + 1, acc["plan"])
                    ws.update_cell(r, col.get("token_balance", 2) + 1, str(acc["token_balance"]))
                    return
            new_row = [""] * len(header)
            new_row[col.get("seller_id", 0)] = sid
            new_row[col.get("plan", 1)] = acc["plan"]
            new_row[col.get("token_balance", 2)] = str(acc["token_balance"])
            ws.append_row(new_row)
            return
        except Exception as exc:
            logger.warning("billing 저장 실패(인메모리 폴백): %s", exc)
    _in_memory[sid] = {"plan": acc["plan"], "token_balance": acc["token_balance"]}


def create_pending_payment(*, seller_id: Optional[str], plan: str, order_id: str, amount: int) -> dict:
    """결제 대기 주문 저장(결제 승인 콜백 검증용)."""
    sid = str(seller_id or "")
    payload = {
        "seller_id": sid,
        "plan": plan if plan in PLANS else "free",
        "order_id": str(order_id or ""),
        "amount": int(amount or 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _pending_payments[payload["order_id"]] = payload
    return payload


def get_pending_payment(order_id: str) -> Optional[dict]:
    item = _pending_payments.get(str(order_id or ""))
    return dict(item) if item else None


def pop_pending_payment(order_id: str) -> Optional[dict]:
    item = _pending_payments.pop(str(order_id or ""), None)
    return dict(item) if item else None
