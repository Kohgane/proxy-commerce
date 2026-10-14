import os

import pytest

_PG = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
pytestmark = pytest.mark.skipif(not _PG, reason="DATABASE_URL 미설정 — PG 테스트 skip")


@pytest.fixture
def L():
    import src.db.pg as pg
    pg.reset_state()
    pg.init_schema()
    with pg.tx() as cur:
        cur.execute("TRUNCATE proxy_orders")
    from src.proxy_buy import ledger
    yield ledger
    pg.reset_state()


def _mk(L, d="gid://d/1"):
    return L.enqueue(source_url="https://www.musinsa.com/p/1", total_usd="100.00", title="후드",
                     email="a@b.com", price_krw=75000, fx=1020, draft_order_id=d)


def test_enqueue_dedup_and_queue(L):
    a = _mk(L)
    b = _mk(L)
    assert a["id"] == b["id"] and len(L.queue()) == 1


def test_cannot_skip_states_or_buy_without_receipt(L):
    o = _mk(L)
    with pytest.raises(ValueError):
        L.transition(o["id"], "purchased", purchase_ref="R1")      # 승인 전 구매 불가
    L.transition(o["id"], "approved")
    with pytest.raises(ValueError):
        L.transition(o["id"], "purchased")                         # 영수증 없음
    L.transition(o["id"], "purchased", purchase_ref="MUSINSA-123", purchase_krw=75000)
    with pytest.raises(ValueError):
        L.transition(o["id"], "shipped")                           # 운송장 없음
    s = L.transition(o["id"], "shipped", carrier="YunExpress", tracking_no="YT123")
    assert s["status"] == "shipped" and s["purchase_ref"] == "MUSINSA-123"
    with pytest.raises(ValueError):
        L.transition(o["id"], "approved")                          # 되돌리기 불가


def test_proof_rows_and_queue_drain(L):
    o = _mk(L)
    L.transition(o["id"], "approved")
    assert L.queue() == []
    L.transition(o["id"], "purchased", purchase_ref="R9")
    L.transition(o["id"], "shipped", carrier="UPS", tracking_no="1Z")
    p = L.proof_rows()
    assert len(p) == 1 and p[0]["purchase_ref"] == "R9" and p[0]["tracking_no"] == "1Z"
