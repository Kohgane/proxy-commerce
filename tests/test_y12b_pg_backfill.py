"""Y12-B(오너 2026-10-17) — PG 경로: 옛 행(요약 없음)에도 「손댈 것 · 수집 실패」·「재수집 대기」 요약이 붙는다.

백필(`oneshot_ops._attn_backfill`)이 수집 실패 후보를 고르고, 「재수집 대기」 필터(`extra_json->'attn' ? 'refetch'`)가 SQL로 돈다.
CI pg-suite 레인(로컬 PostgreSQL)에서만 돈다.
"""
from __future__ import annotations

import os

import pytest

from src.seller_console import collect_history_store as S
from tests.test_y12b_attention import EXHAUSTED, WAIT_PC, _add

_PG_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
_has_pg = bool(_PG_URL and _PG_URL.startswith("postgres"))


@pytest.mark.skipif(not _has_pg, reason="로컬 PostgreSQL(DATABASE_URL) 설정 시만")
def test_pg_backfill_picks_failure_candidates_and_refetch_filter(monkeypatch):
    """옛 행(요약 없음)에도 수집 실패 요약이 붙는다 — 백필이 실패 후보를 고르고, 「재수집 대기」 필터가 SQL로 돈다."""
    from src.db import pg
    from src.db import collect_history_pg as P
    pg.reset_state(); pg.init_schema()
    uid = "u-y12b-pg"
    ex_id = _add(uid, dict(EXHAUSTED), url="https://item.taobao.com/item.htm?id=901")
    wt_id = _add(uid, dict(WAIT_PC), url="https://item.taobao.com/item.htm?id=902")
    bare_id = _add(uid, {"title": "빈 수집"}, url="https://item.taobao.com/item.htm?id=903")
    ok_id = _add(uid, {"price": "10", "images": ["https://img.alicdn.com/a.jpg"]}, url="https://item.taobao.com/item.htm?id=904")
    with pg.tx() as cur:                                         # 옛 행처럼 — 요약·열을 비운다
        cur.execute("UPDATE collect_history SET attn_n=0, last_action_at=NULL, extra_json = extra_json - 'attn' "
                    "WHERE user_id=%s", [uid])
    picked = {i for i, _u in P.ids_for_attention_backfill()}
    assert {ex_id, wt_id, bare_id} <= picked and ok_id not in picked
    from src.services import oneshot_ops as O
    assert O._attn_backfill()["ok"]
    assert {r["id"] for r in S.list_items(days=3650, seller_ids={uid}, attn_only=True)} == {ex_id, bare_id}
    assert S.count_items(days=3650, seller_ids={uid}, refetch_only=True) == 1
    assert [r["id"] for r in S.list_items(days=3650, seller_ids={uid}, refetch_only=True)] == [wt_id]
    with pg.tx() as cur:
        cur.execute("DELETE FROM collect_history WHERE user_id=%s", [uid])


@pytest.mark.skipif(not _has_pg, reason="로컬 PostgreSQL(DATABASE_URL) 설정 시만")
def test_pg_dashboard_rows_small_columns_and_ledger_account_counts():
    """Y12-C — 대시보드 한 쿼리가 작은 칸만 싣고(사진 기록 통째 X, 다듬기 시각만) · 대장 계정별 건수가 임시저장 반려를 `held`로 가른다."""
    import json
    from src.db import pg
    from src.db import collect_history_pg as P
    from src.db import market_registrations_pg as L
    from src.seller_console import home_bundles as H
    pg.reset_state(); pg.init_schema()
    uid = "u-y12c-pg"
    ex = {"title_ko": "VRSUK{비즈니스}", "price": "1", "images": ["https://img.alicdn.com/a.jpg"],
          "uploaded": [{"market": "coupang:woojoo", "account": "woojoo", "product_id": "9", "at": "2026-10-15T15:38:55+00:00",
                        "review": {"state": "approved", "status_raw": "승인완료", "checked_at": "2026-10-17T17:10:20+00:00"}}],
          "detail_images_ko": [{"idx": i, "big": "x" * 5000,
                                "polish": {"at": f"2026-10-15T06:39:{10 + i:02d}+00:00", "version": "edit:1"}} for i in range(2)]}
    iid = _add(uid, ex, url="https://item.taobao.com/item.htm?id=905")
    rows = [r for r in P.dashboard_rows(seller_ids={uid}) if r["id"] == iid]
    assert len(rows) == 1
    small = rows[0]["extra"]
    assert sorted(small["_polish_ats"]) == ["2026-10-15T06:39:10+00:00", "2026-10-15T06:39:11+00:00"]
    assert "detail_images_ko" not in small and len(json.dumps(small)) < 2000
    assert H._markets(rows)["rows"][1]["sale"] == 1
    with pg.tx() as cur:
        cur.execute("DELETE FROM market_registrations WHERE product_id IN ('y12c-a', 'y12c-b')")
    L.record("y12c-a", account="gogane", title="andobil")
    L.mark_checked("y12c-a", status="approved")
    L.record("y12c-b", account="gogane", title="Stagg")
    L.mark_checked("y12c-b", status="rejected", reject_kind="unknown", reject_comment="판매자(A01381223) 임시저장")
    got = {(c["status"], c["held"]): c["n"] for c in L.account_counts(marketplace="coupang") if c["account"] == "gogane"}
    assert got.get(("approved", False), 0) >= 1 and got.get(("rejected", True), 0) >= 1
    with pg.tx() as cur:
        cur.execute("DELETE FROM market_registrations WHERE product_id IN ('y12c-a', 'y12c-b')")
        cur.execute("DELETE FROM collect_history WHERE user_id=%s", [uid])
