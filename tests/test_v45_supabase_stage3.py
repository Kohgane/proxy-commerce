"""tests/test_v45_supabase_stage3.py — 이관 3단계: orders(주문·정산 파생) → Postgres.

SheetsOrderAdapter가 pg_enabled면 orders_pg로 위임. (order_id,marketplace) upsert·필터·운송장/상태
갱신·KPI. 검증: upsert→재시작 유지·중복0·운송장 영속·상태 갱신·KPI 파생.
SUPABASE_DB_URL/DATABASE_URL 설정 시에만(미설정=Sheets 폴백, skip).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

_PG = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
pytestmark = pytest.mark.skipif(not _PG, reason="DATABASE_URL 미설정 — PG 이관 테스트 skip")


@pytest.fixture
def adapter():
    import src.db.pg as pg
    pg.reset_state()
    assert pg.pg_enabled()
    pg.init_schema()
    with pg.tx() as cur:
        cur.execute("TRUNCATE orders")
    from src.seller_console.orders.sheets_adapter import OrderSheetsAdapter
    yield OrderSheetsAdapter(), pg
    pg.reset_state()


def _order(oid, mp, status, total="10000", items=None):
    from src.seller_console.orders.models import UnifiedOrder, OrderStatus, OrderLineItem
    return UnifiedOrder(order_id=oid, marketplace=mp, status=OrderStatus(status),
                        placed_at=datetime.now(timezone.utc), total_krw=Decimal(total),
                        items=items or [])


def test_upsert_dedup_and_persist(adapter):
    a, pg = adapter
    from src.seller_console.orders.models import OrderLineItem
    o1 = _order("ORD1", "coupang", "paid", items=[OrderLineItem(sku="S1", title="t", qty=1, unit_price_krw=Decimal("10000"), options={})])
    o2 = _order("ORD2", "smartstore", "new")
    assert a.bulk_upsert([o1, o2]) == 2
    assert a.bulk_upsert([o1]) == 1                # 같은 키 → update
    q = a.query(limit=50)
    assert len(q) == 2                             # 중복 0
    # 재시작 후에도 유지
    pg.reset_state()
    assert {o.order_id for o in a.query(limit=50)} == {"ORD1", "ORD2"}


def test_filter_and_tracking_persist(adapter):
    a, pg = adapter
    a.bulk_upsert([_order("ORD1", "coupang", "paid"), _order("ORD2", "smartstore", "new")])
    assert len(a.query(filters={"marketplace": "coupang"})) == 1
    assert a.update_tracking("ORD1", "coupang", "CJ", "999") is True
    pg.reset_state()
    got = {o.order_id: o for o in a.query(limit=50)}
    assert got["ORD1"].tracking_no == "999"
    assert (got["ORD1"].status.value if hasattr(got["ORD1"].status, "value") else got["ORD1"].status) == "shipped"


def test_status_update_and_kpi(adapter):
    a, pg = adapter
    a.bulk_upsert([_order("ORD1", "coupang", "paid"), _order("ORD2", "smartstore", "new")])
    a.update_status("ORD1", "coupang", "shipped", note="발송")
    a.update_status("ORD2", "smartstore", "preparing")
    kpi = a.kpi_summary()
    assert kpi["shipped"] == 1 and kpi["pending_ship"] == 1


def test_missing_order_update_false(adapter):
    a, _pg = adapter
    assert a.update_tracking("NOPE", "coupang", "CJ", "1") is False
    assert a.update_status("NOPE", "coupang", "shipped") is False


def test_fallback_contract_source():
    from pathlib import Path
    src = Path("src/seller_console/orders/sheets_adapter.py").read_text(encoding="utf-8")
    assert "def _pg_orders()" in src
    # PG-only 전환: 어댑터가 PG 또는 인메모리 백엔드로 위임(Sheets 제거)
    assert "_order_backend()" in src and ".upsert_rows(" in src and ".all_row_dicts()" in src
    sch = Path("src/db/schema_stage3.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS orders" in sch and "uq_orders_key" in sch
