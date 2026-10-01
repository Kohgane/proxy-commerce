"""O(오너 2026-10-01) — 공유 버전별 도착 카운터가 **실제 Postgres에서** 쌓인다(pg-suite 레인).

실측(로컬 PG 16 · psycopg3): 고치기 전 SQL은 `IndeterminateDatatype: could not determine data type of
parameter $2`로 거부됐고, 호출부 except가 삼켜 운영 `app_state`에 `help:share_version_counts`가 한 번도
생기지 않았다. 인메모리 레인에선 PG 분기를 안 타서 계약이 늘 초록이었다 — 그래서 이 계약은 PG에서만 돈다.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def pg_ready():
    from src.db import pg
    if not pg.pg_enabled():
        pytest.skip("DATABASE_URL 없음 — CI pg-suite 레인에서 돈다")
    pg.init_schema()
    with pg.tx() as cur:
        cur.execute("DELETE FROM app_state WHERE key IN (%s, %s) OR key LIKE %s OR key LIKE %s",
                    ("help:share_version_counts", "help:share_arrivals", "share_ticket:%", "share_in_rl:%"))
    yield


def test_version_counter_persists_on_postgres(pg_ready):
    from src.seller_console.help_settings import bump_share_version, share_version_counts
    bump_share_version(2)
    bump_share_version(2)
    bump_share_version(0)
    assert share_version_counts() == {"v2": 2, "v0": 1}


def test_arrival_log_persists_on_postgres(pg_ready):
    from src.seller_console.help_settings import record_share_arrival, share_arrivals
    for i in range(22):
        record_share_arrival({"at": f"t{i}", "v": 2, "qlen": i, "text_len": 0, "clip_len": 0, "stage": "recv"})
    rows = share_arrivals()
    assert len(rows) == 20 and rows[0]["at"] == "t21"


def test_share_tickets_and_rate_limit_on_postgres(pg_ready):
    """P2 — 티켓·IP 레이트가 **워커 공유 저장소**(app_state)에서 돈다: 10건 뒤 상한 · 만료분 정리."""
    from src.db import pg
    from src.seller_console import share_tickets as T
    with pg.tx() as cur:
        cur.execute("DELETE FROM app_state WHERE key LIKE %s OR key LIKE %s", ("share_ticket:%", "share_in_rl:%"))
    t = T.create("你好 https://e.tb.cn/h.x?tk=Z", ip="198.51.100.7")
    assert T.read(t) == {"ok": True, "text": "你好 https://e.tb.cn/h.x?tk=Z", "reason": "", "used": False}
    for _ in range(9):
        T.create("a", ip="198.51.100.7")
    with pytest.raises(T.RateLimited):
        T.create("a", ip="198.51.100.7")
    with pg.tx() as cur:
        cur.execute("UPDATE app_state SET updated_at = now() - interval '20 minutes' WHERE key LIKE %s", ("share_ticket:%",))
    T.prune()
    with pg.query() as cur:
        cur.execute("SELECT count(*) FROM app_state WHERE key LIKE %s", ("share_ticket:%",))
        assert cur.fetchone()[0] == 0
