"""tests/test_v49_db_metering.py — v49 STEP2: DB 왕복 계측(쿼리수·개별ms·Server-Timing) + 다이어트.

요청당 총 쿼리 수·개별 쿼리 ms를 Server-Timing(dbq;desc="N queries")·로그에 노출(N+1 진단).
상시 커넥션 풀은 PG_PERSISTENT_POOL=1일 때만(기본 OFF, 무회귀). 뷰 레벨 db 이중계상 제거.
DB 없는(인메모리) 경로는 소스 계약만, PG 경로는 로컬 PostgreSQL 설정 시만 실측.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

PG = Path("src/db/pg.py").read_text(encoding="utf-8")
PERF = Path("src/utils/perf.py").read_text(encoding="utf-8")
LOG = Path("src/middleware/request_logger.py").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")

_PG_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
_has_pg = bool(_PG_URL and _PG_URL.startswith("postgres"))


def test_source_contract_metering():
    # pg 레이어가 쿼리별 시간 계측(_timed_db) + 총 쿼리 수 카운트(db_query)
    assert "_timed_db" in PG and "perf_add_ms" in PG
    assert 'perf_count("db_query"' in PG
    # 개별 ms 리스트 API
    assert "def perf_add_ms" in PERF and "def perf_ms_list" in PERF
    # Server-Timing에 쿼리 수(dbq) + 로그에 개별 ms
    assert 'dbq;desc=' in LOG and "db_ms_each" in LOG
    # 뷰 레벨 db 이중계상 제거(collect_history는 pg 레이어 계측만)
    assert "뷰 레벨 perf_block" in VIEWS


def test_source_contract_pool_gated():
    # 상시 풀은 PG_PERSISTENT_POOL 게이트 안에만(기본 OFF, 무회귀)
    assert "PG_PERSISTENT_POOL" in PG and "_persistent_pool" in PG
    assert "psycopg_pool" in PG and "putconn" in PG
    # 게이트: 미설정이면 즉시 None 반환(기본 OFF)
    assert 'os.getenv("PG_PERSISTENT_POOL", "0") != "1":\n        return None' in PG


@pytest.mark.skipif(not _has_pg, reason="로컬 PostgreSQL(DATABASE_URL) 설정 시만")
def test_query_count_and_timing_measured():
    # 실 PG로 수집이력 페이지의 쿼리 수·개별 ms·연결 수를 계측(목표 ≤3 쿼리, 1 연결).
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    os.environ.pop("PG_PERSISTENT_POOL", None)
    from src.db import pg
    pg.reset_state(); pg.init_schema()
    from src.seller_console import collect_history_store as ch
    ch.append(source="extension", url="https://x/g-1", title="A", price="100", currency="KRW",
              status="ok", seller_id="u1", extra={"title_ko": "A"})
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
        r = c.get("/seller/collect/history")
        st = r.headers.get("Server-Timing", "")
        assert r.status_code == 200
        assert 'dbq;desc=' in st            # 쿼리 수 노출
        # 요청범위 연결 재사용 → 페이지당 연결 1개(핸드셰이크 1회)
        import re
        m = re.search(r'dbconn;desc=(\d+)', st)
        assert m and int(m.group(1)) == 1, st
        # 쿼리 수 ≤3(list+summary+distinct)
        mq = re.search(r'dbq;desc="(\d+) queries"', st)
        assert mq and int(mq.group(1)) <= 3, st


@pytest.mark.skipif(not _has_pg, reason="로컬 PostgreSQL 설정 시만")
def test_persistent_pool_no_handshake():
    # PG_PERSISTENT_POOL=1 → 풀 대여(재요청 시 핸드셰이크 0 = dbconn 헤더 없음).
    pytest.importorskip("psycopg_pool")
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    os.environ["PG_PERSISTENT_POOL"] = "1"
    try:
        from src.db import pg
        pg.reset_state()
        from src.order_webhook import app
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
            c.get("/seller/collect/history")               # 풀 워밍업
            r = c.get("/seller/collect/history")
            st = r.headers.get("Server-Timing", "")
            assert "dbconn;desc=" not in st, ("풀 대여는 새 핸드셰이크 아님", st)
    finally:
        os.environ.pop("PG_PERSISTENT_POOL", None)
        from src.db import pg
        pg.reset_state()
