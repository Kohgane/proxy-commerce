"""src/db/orders_pg.py — 주문(orders) Postgres 백엔드(이관 3단계).

SheetsOrderAdapter가 pg_enabled면 이리로 위임. 행 dict는 ORDERS_HEADERS 키(시트와 동일)라
어댑터의 _row_to_order/_order_to_row·필터·KPI 로직을 그대로 재사용한다. 트랜잭션 커밋 후에만 성공.
키=(order_id, marketplace) upsert. 정산 KPI(마진 등)는 이 행에서 파생(별도 테이블 불필요).
"""
from __future__ import annotations

import logging

from . import pg

logger = logging.getLogger(__name__)

# 저장 컬럼(= ORDERS_HEADERS). 시트 행 dict와 1:1.
_COLS = [
    "order_id", "marketplace", "status", "placed_at", "paid_at",
    "buyer_name_masked", "buyer_phone_masked", "buyer_address_masked",
    "total_krw", "shipping_fee_krw", "items_json", "courier", "tracking_no",
    "shipped_at", "landed_cost_krw", "margin_krw", "margin_pct", "last_synced_at", "notes",
    # v87-S2 후속 통관 축. 아직 이 값을 채우는 동기화 배선이 없어 실서비스에선 빈 값이다 —
    # 그래서 화면이 '미수신'으로 표기한다(빈 값을 숨겨서 필드가 없는 척하지 않는다).
    "pcc", "country",
    # v87-S4 드로어 3칩 대상 주소. 채워지면 칩이 살고, 비면 '원본 미연결' 비활성으로 남는다.
    "source_url", "market_url", "detail_url",
]


def upsert_rows(rows: list) -> int:
    """행 dict(ORDERS_HEADERS 키) 목록을 (order_id, marketplace)로 upsert. 처리 건수 반환."""
    n = 0
    with pg.tx() as cur:
        for r in rows or []:
            vals = [str(r.get(c, "") if r.get(c) is not None else "") for c in _COLS]
            set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in _COLS if c not in ("order_id", "marketplace"))
            cur.execute(
                f"""INSERT INTO orders ({', '.join(_COLS)})
                    VALUES ({', '.join(['%s'] * len(_COLS))})
                    ON CONFLICT (order_id, marketplace) WHERE deleted_at IS NULL
                    DO UPDATE SET {set_clause}""",
                vals)
            n += 1
    return n


def all_row_dicts() -> list:
    """활성 주문 전부를 ORDERS_HEADERS 키 dict로 반환(어댑터가 필터/정렬/KPI에 재사용)."""
    with pg.query() as cur:
        cur.execute(f"SELECT {', '.join(_COLS)} FROM orders WHERE deleted_at IS NULL")
        return [dict(zip(_COLS, row)) for row in cur.fetchall()]


def update_tracking(order_id: str, marketplace: str, courier: str, tracking_no: str, shipped_status: str) -> bool:
    with pg.tx() as cur:
        cur.execute(
            "UPDATE orders SET courier=%s, tracking_no=%s, status=%s WHERE order_id=%s AND marketplace=%s AND deleted_at IS NULL RETURNING id",
            (courier, tracking_no, shipped_status, order_id, marketplace))
        return cur.fetchone() is not None


def update_status(order_id: str, marketplace: str, status: str, note: str, last_synced_at: str) -> bool:
    with pg.tx() as cur:
        cur.execute("SELECT notes FROM orders WHERE order_id=%s AND marketplace=%s AND deleted_at IS NULL LIMIT 1",
                    (order_id, marketplace))
        r = cur.fetchone()
        if not r:
            return False
        notes = str(r[0] or "")
        if note:
            notes = (f"{notes} | {note}" if notes.strip() else note)[-2000:]
        cur.execute("UPDATE orders SET status=%s, notes=%s, last_synced_at=%s WHERE order_id=%s AND marketplace=%s AND deleted_at IS NULL RETURNING id",
                    (status, notes, last_synced_at, order_id, marketplace))
        return cur.fetchone() is not None
