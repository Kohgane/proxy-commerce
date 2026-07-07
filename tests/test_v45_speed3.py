"""tests/test_v45_speed3.py — 속도3: 연결 재사용 + FX 캐시 + summary/distinct SQL 집계 + SQL 페이지.

오너: 병목을 수치로 지목 후 순서대로 수리. 로컬 PG 실측: 드로어 361→18.6ms(19×, 6→1연결),
목록 64.8→30.5ms(3→1연결), 무한스크롤 조각 119→18.6ms. FX 반복 외부호출·연결당 핸드셰이크·
summary 전체스캔이 병목이었다.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

PG = Path("src/db/pg.py").read_text(encoding="utf-8")
CHPG = Path("src/db/collect_history_pg.py").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
DA = Path("src/seller_console/data_aggregator.py").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _mem():
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    yield


def test_request_scoped_connection_reuse():
    # query()가 요청 범위 내 읽기 연결 1개를 재사용(핸드셰이크 N→1) + teardown에서 닫는다.
    assert "_request_read_conn" in PG and "_kgp_db_read_conn" in PG
    assert "close_request_conn" in PG
    OW = Path("src/order_webhook.py").read_text(encoding="utf-8")
    assert "teardown_request" in OW and "close_request_conn" in OW


def test_query_count_exposed():
    # db 연결/쿼리 수를 perf_count로 세고 Server-Timing/로그에 노출(N+1 진단).
    assert "perf_count" in PG
    RL = Path("src/middleware/request_logger.py").read_text(encoding="utf-8")
    assert "dbconn" in RL and "perf_count" in RL


def test_summary_distinct_use_sql_aggregation():
    # summary/distinct_domains가 전체 행을 파이썬으로 세지 않고 SQL 집계.
    assert "count(*) FILTER" in CHPG                 # summary 집계
    assert "SELECT DISTINCT domain" in CHPG          # distinct는 SQL
    # summary가 더는 list_items(전체)로 세지 않는다
    seg = CHPG[CHPG.index("def summary("):CHPG.index("def distinct_domains(")]
    assert "list_items(" not in seg


def test_list_items_supports_limit_offset():
    from src.seller_console.collect_history_store import list_items, append, _in_memory
    _in_memory.clear()
    for i in range(10):
        append(source="extension", url=f"https://x.com/g-{i}", title=f"t{i}", seller_id="s1")
    page = list_items(seller_ids={"s1"}, limit=3, offset=0)
    assert len(page) == 3
    page2 = list_items(seller_ids={"s1"}, limit=3, offset=3)
    assert len(page2) == 3 and page2[0]["id"] != page[0]["id"]


def test_view_sql_page_fastpath():
    # 기본 뷰(최신순·필터없음)는 SQL LIMIT 경로, 조각은 summary/distinct 생략.
    assert "_sql_page" in VIEWS
    assert "limit=per_page, offset=offset" in VIEWS
    assert 'if fmt != "rows":' in VIEWS


def test_fx_rates_cached():
    from src.seller_console import data_aggregator as da
    da._FX_CACHE["data"] = None; da._FX_CACHE["ts"] = 0.0
    a = da.get_fx_rates()
    b = da.get_fx_rates()
    assert a is b                    # 두 번째는 캐시(같은 객체) — 외부 재호출 없음
    assert "_FX_CACHE" in DA and "_compute_fx_rates" in DA
