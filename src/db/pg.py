"""src/db/pg.py — Supabase Postgres 접속 레이어 (Google Sheets → Postgres 이관 1단계).

접속정보는 **환경변수로만**(하드코딩 금지): SUPABASE_DB_URL 또는 DATABASE_URL(둘 다 표준 libpq URL).
미설정/드라이버 없음이면 pg_enabled()=False → 호출자는 기존 Sheets/인메모리 경로로 폴백(무회귀).

- 트랜잭션 커밋 후에만 성공: `with tx() as cur:` 블록이 정상 종료 시 commit, 예외 시 rollback.
- 스키마 부트스트랩(init_schema): 1단계 테이블(collect_history, user_tokens) DDL을 idempotent 적용.
- 시크릿 미로깅.
"""
from __future__ import annotations

import contextlib
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_pool = None
_checked = False
_available = False


def db_url() -> str:
    """런타임 접속 URL — Supabase 트랜잭션 풀러(포트 6543) 권장. 없으면 ''."""
    return (os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or "").strip()


def direct_url() -> str:
    """DDL·마이그레이션용 **직접 연결**(포트 5432) URL.

    Supabase 트랜잭션 풀러(6543)는 prepared statement/DDL 이슈가 있어, 스키마 생성·마이그레이션은
    Direct connection(대시보드의 5432 URL)을 별도 env(DATABASE_URL_DIRECT)로 받아 쓴다. 미설정이면
    풀러 URL로 폴백(로컬/단일 PG는 구분 없음).
    """
    return (os.getenv("DATABASE_URL_DIRECT") or "").strip() or db_url()


def pg_enabled() -> bool:
    """Postgres 사용 가능 여부 — URL 설정 + psycopg2 임포트 가능 + 최초 접속 성공."""
    global _checked, _available
    if _checked:
        return _available
    with _lock:
        if _checked:
            return _available
        _checked = True
        _available = False
        url = db_url()
        if not url:
            return False
        try:
            import psycopg2  # noqa: F401
        except Exception as exc:   # 드라이버 미설치 — 폴백
            logger.warning("psycopg2 미설치 — Sheets 폴백: %s", exc)
            return False
        try:
            conn = _connect(url)
            conn.close()
            _available = True
            logger.info("Postgres 연결 성공 — 이관 백엔드 활성")
        except Exception as exc:
            logger.warning("Postgres 연결 실패 — Sheets 폴백: %s", exc)
            _available = False
        return _available


def reset_state():
    """테스트용 — 캐시된 가용성/풀 초기화."""
    global _checked, _available, _pool
    with _lock:
        _checked = False
        _available = False
        if _pool is not None:
            try:
                _pool.closeall()
            except Exception:
                pass
        _pool = None


def _connect(url: str):
    import psycopg2
    return psycopg2.connect(url, connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "10") or 10))


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _lock:
        if _pool is None:
            from psycopg2.pool import ThreadedConnectionPool
            _pool = ThreadedConnectionPool(
                1, int(os.getenv("PG_POOL_MAX", "8") or 8), dsn=db_url())
    return _pool


@contextlib.contextmanager
def get_conn():
    """풀에서 커넥션을 빌려주고 반납.

    트랜잭션 풀러(6543) 호환: 반납 전 `rollback()`으로 열린 트랜잭션을 반드시 정리한다
    (idle-in-transaction·prepared statement 잔류 방지). tx()는 이미 commit했으므로 no-op.
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        pool.putconn(conn)


@contextlib.contextmanager
def tx():
    """트랜잭션 — 블록 정상 종료 시 commit, 예외 시 rollback. (커밋 후에만 성공 응답)"""
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise


@contextlib.contextmanager
def query():
    """읽기 전용 커서."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            yield cur


_SCHEMA_FILE = Path(__file__).with_name("schema_stage1.sql")
_schema_done = False


@contextlib.contextmanager
def direct_conn():
    """마이그레이션용 **직접 연결(5432)** 1회용 컨텍스트 — 정상 종료 시 commit, 예외 시 rollback."""
    conn = _connect(direct_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_ddl(ddl: str):
    """DDL을 **직접 연결(5432)** 로 실행 — 트랜잭션 풀러의 DDL/prepared 이슈 회피."""
    conn = _connect(direct_url())
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(ddl)
    finally:
        conn.close()


def init_schema():
    """1단계 스키마를 idempotent 적용(collect_history, user_tokens). 직접 연결로 실행."""
    global _schema_done
    if _schema_done or not pg_enabled():
        return
    run_ddl(_SCHEMA_FILE.read_text(encoding="utf-8"))
    _schema_done = True
    logger.info("Postgres 1단계 스키마 적용 완료(직접 연결)")
