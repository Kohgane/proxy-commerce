"""구매대행 주문 대장 — 승인 큐 + 증빙(주문번호 ↔ 구매영수증 ↔ 운송장). Postgres 필수.

상태 전이는 허용된 것만(건너뛰기·되돌리기 금지) — 영수증 없이 purchased, 운송장 없이 shipped 불가.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.db import pg

NEXT = {
    "awaiting_approval": {"approved", "refused", "cancelled"},
    "approved": {"purchased", "cancelled"},
    "purchased": {"shipped"},
    "shipped": {"delivered"},
}
_COLS = ("id,draft_order_id,shopify_order,email,source_url,title,total_usd,price_krw,fx_krw_per_usd,"
         "status,purchase_ref,purchase_krw,carrier,tracking_no,note,created_at")


def _row(cur) -> Optional[Dict[str, Any]]:
    r = cur.fetchone()
    if not r:
        return None
    keys = [c.name for c in cur.description]
    return {k: (str(v) if k in ("id", "total_usd", "fx_krw_per_usd") or hasattr(v, "isoformat") else v)
            for k, v in zip(keys, r)}


def enqueue(*, source_url: str, total_usd, title: str = "", email: str = "", price_krw: int = 0,
            fx: float = 0, draft_order_id: str = "") -> Dict[str, Any]:
    """승인 대기 큐에 넣는다(같은 draft는 한 번만)."""
    with pg.tx() as cur:
        if draft_order_id:
            cur.execute(f"SELECT {_COLS} FROM proxy_orders WHERE draft_order_id=%s", (draft_order_id,))
            ex = _row(cur)
            if ex:
                return ex
        cur.execute(
            f"INSERT INTO proxy_orders (draft_order_id,email,source_url,title,total_usd,price_krw,fx_krw_per_usd) "
            f"VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING {_COLS}",
            (draft_order_id, email, source_url, title, total_usd, price_krw, fx))
        return _row(cur)


def queue() -> List[Dict[str, Any]]:
    with pg.tx() as cur:
        cur.execute(f"SELECT {_COLS} FROM proxy_orders WHERE status='awaiting_approval' ORDER BY created_at")
        out = []
        while True:
            r = _row(cur)
            if not r:
                return out
            out.append(r)


def transition(order_id: str, to: str, *, purchase_ref: str = "", purchase_krw: Optional[int] = None,
               carrier: str = "", tracking_no: str = "", note: str = "") -> Dict[str, Any]:
    with pg.tx() as cur:
        cur.execute("SELECT status, purchase_ref, tracking_no FROM proxy_orders WHERE id=%s FOR UPDATE", (order_id,))
        row = cur.fetchone()
        if not row:
            raise KeyError("no such order")
        cur_status, have_ref, have_trk = row
        if to not in NEXT.get(cur_status, set()):
            raise ValueError(f"{cur_status} -> {to} 전이 불가")
        if to == "purchased" and not (purchase_ref or have_ref):
            raise ValueError("구매 영수증/주문번호 없이 purchased 불가")
        if to == "shipped" and not (tracking_no or have_trk):
            raise ValueError("운송장 없이 shipped 불가")
        cur.execute(
            f"UPDATE proxy_orders SET status=%s, "
            f"purchase_ref=COALESCE(NULLIF(%s,''),purchase_ref), purchase_krw=COALESCE(%s,purchase_krw), "
            f"carrier=COALESCE(NULLIF(%s,''),carrier), tracking_no=COALESCE(NULLIF(%s,''),tracking_no), "
            f"note=COALESCE(NULLIF(%s,''),note), updated_at=now() WHERE id=%s RETURNING {_COLS}",
            (to, purchase_ref, purchase_krw, carrier, tracking_no, note, order_id))
        return _row(cur)


def proof_rows() -> List[Dict[str, Any]]:
    """증빙표 — 구매·발송까지 간 주문의 주문번호 ↔ 영수증 ↔ 운송장."""
    with pg.tx() as cur:
        cur.execute("SELECT shopify_order, draft_order_id, purchase_ref, carrier, tracking_no, status "
                    "FROM proxy_orders WHERE status IN ('purchased','shipped','delivered') ORDER BY created_at")
        return [dict(zip([c.name for c in cur.description], r)) for r in cur.fetchall()]
