"""tests/test_v45_supabase_conn.py — Supabase 연결 규칙(오너 운영 지침) · psycopg3/NullPool.

런타임=풀러(6543, DATABASE_URL) · DDL/마이그레이션=직접 연결(5432, DATABASE_URL_DIRECT).
psycopg3 + NullPool(매 작업 새 연결·close) + prepared statement 비활성(풀러 호환).
PG 불필요 — env 로직 + 소스 계약만 검증.
"""
from __future__ import annotations

from pathlib import Path

import src.db.pg as pg

PGSRC = Path("src/db/pg.py").read_text(encoding="utf-8")
MIG = Path("scripts/migrate_to_supabase.py").read_text(encoding="utf-8")


def test_runtime_url_prefers_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://pooler:6543/db")
    monkeypatch.setenv("DATABASE_URL_DIRECT", "postgresql://direct:5432/db")
    assert pg.db_url().endswith(":6543/db")          # 런타임=풀러
    assert pg.direct_url().endswith(":5432/db")       # DDL=직접


def test_direct_url_falls_back_to_runtime(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://pooler:6543/db")
    monkeypatch.delenv("DATABASE_URL_DIRECT", raising=False)
    assert pg.direct_url() == pg.db_url()             # 미설정이면 폴백


def test_ddl_runs_via_direct_connection_and_split():
    assert "def run_ddl(" in PGSRC
    i = PGSRC.index("def run_ddl")
    blk = PGSRC[i:i + 600]
    assert "direct_url()" in blk                      # DDL은 직접 연결
    assert "_split_sql" in blk                        # 다중 문장 분할(psycopg3 확장 프로토콜)


def test_psycopg3_nullpool_and_no_prepared():
    # psycopg3 사용 + prepared statement 비활성(트랜잭션 풀러 호환)
    assert "import psycopg" in PGSRC and "prepare_threshold=None" in PGSRC
    # NullPool: 영속 풀 없음(psycopg2 풀 API 미사용). 매 작업 새 연결 후 close 원칙 유지.
    assert "ThreadedConnectionPool" not in PGSRC and "getconn" not in PGSRC
    # tx()·get_conn()은 1회용(즉시 close). query()는 속도 최적화로 요청 범위 내 읽기 연결을 재사용하되
    #   요청 종료 시 close_request_conn(teardown)로 닫는다(연결 누수 0) + 요청 밖 1회용 경로는 즉시 close.
    for fn in ("def tx(", "def get_conn("):
        j = PGSRC.index(fn)
        assert "conn.close()" in PGSRC[j:j + 400], fn
    assert "close_request_conn" in PGSRC          # 요청 범위 재사용 연결의 명시적 종료
    assert "conn.close()" in PGSRC[PGSRC.index("def query("):]   # query 1회용 경로도 close


def test_migration_uses_direct_conn():
    assert "pg.direct_conn()" in MIG                  # 마이그레이션은 직접 연결
    assert "def direct_conn(" in PGSRC


def test_boot_log_line_present():
    assert 'logger.info("DB 연결: Supabase OK")' in PGSRC
