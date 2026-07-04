"""tests/test_v45_supabase_conn.py — Supabase 연결 규칙(오너 운영 지침).

런타임=풀러(6543, SUPABASE_DB_URL) · DDL/마이그레이션=직접 연결(5432, DATABASE_URL_DIRECT).
PG 불필요 — env 로직 + 소스 계약만 검증.
"""
from __future__ import annotations

from pathlib import Path

import src.db.pg as pg

PGSRC = Path("src/db/pg.py").read_text(encoding="utf-8")
MIG = Path("scripts/migrate_to_supabase.py").read_text(encoding="utf-8")


def test_direct_url_prefers_direct_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://pooler:6543/db")
    monkeypatch.setenv("DATABASE_URL_DIRECT", "postgresql://direct:5432/db")
    assert pg.db_url().endswith(":6543/db")
    assert pg.direct_url().endswith(":5432/db")     # DDL은 직접 연결


def test_direct_url_falls_back_to_runtime(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://pooler:6543/db")
    monkeypatch.delenv("DATABASE_URL_DIRECT", raising=False)
    assert pg.direct_url() == pg.db_url()           # 미설정이면 폴백


def test_ddl_runs_via_direct_connection():
    # init_schema → run_ddl(직접 연결). run_ddl은 direct_url()로 연결.
    assert "def run_ddl(" in PGSRC
    assert "_connect(direct_url())" in PGSRC
    i = PGSRC.index("def init_schema")
    assert "run_ddl(" in PGSRC[i:i + 400]


def test_get_conn_rollback_on_return_for_pooler_safety():
    i = PGSRC.index("def get_conn")
    blk = PGSRC[i:i + 500]
    assert "conn.rollback()" in blk                 # idle-in-transaction 정리(풀러 호환)


def test_migration_uses_direct_conn():
    assert "pg.direct_conn()" in MIG                # 마이그레이션은 직접 연결
    assert "def direct_conn(" in PGSRC
