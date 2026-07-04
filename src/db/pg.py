"""src/db/pg.py — Supabase Postgres 접속 레이어 (Google Sheets → Postgres 이관).

접속정보는 **환경변수로만**(하드코딩 금지):
- 런타임: `DATABASE_URL`(Supabase 트랜잭션 풀러, 포트 6543). (구 `SUPABASE_DB_URL`도 허용.)
- DDL·마이그레이션: `DATABASE_URL_DIRECT`(Direct connection, 포트 5432).
미설정/드라이버 없음이면 pg_enabled()=False → 호출자는 기존 Sheets/인메모리 경로로 폴백(무회귀).

드라이버: **psycopg3**. 트랜잭션 풀러(6543) 호환을 위해
- **NullPool**(클라이언트 풀 없음 — 매 작업마다 새 연결 후 close). 풀러가 서버측 풀링 담당.
- `prepare_threshold=None`(서버측 prepared statement 미사용) — 트랜잭션 풀러의 prepared 이슈 회피.
- 트랜잭션 커밋 후에만 성공: `with tx() as cur:` 정상 종료 시 commit, 예외 시 rollback.
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
_checked = False
_available = False


def db_url() -> str:
    """런타임 접속 URL — Supabase 트랜잭션 풀러(6543, DATABASE_URL). 없으면 ''."""
    return (os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL") or "").strip()


def direct_url() -> str:
    """DDL·마이그레이션용 **직접 연결(5432)** URL(DATABASE_URL_DIRECT). 미설정이면 런타임 URL 폴백."""
    return (os.getenv("DATABASE_URL_DIRECT") or "").strip() or db_url()


def _connect(url: str, *, autocommit: bool = False):
    """psycopg3 연결 — NullPool(1회용) + prepared statement 비활성(풀러 호환)."""
    import psycopg
    return psycopg.connect(
        url,
        autocommit=autocommit,
        prepare_threshold=None,   # 트랜잭션 풀러(6543)에서 prepared statement 미사용
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "10") or 10),
    )


def pg_enabled() -> bool:
    """Postgres 사용 가능 여부 — URL 설정 + psycopg3 임포트 가능 + 최초 접속 성공."""
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
            import psycopg  # noqa: F401
        except Exception as exc:
            logger.warning("psycopg3 미설치 — Sheets 폴백: %s", exc)
            return False
        try:
            conn = _connect(url, autocommit=True)
            conn.close()
            _available = True
            logger.info("DB 연결: Supabase OK")
        except Exception as exc:
            logger.warning("Postgres 연결 실패 — Sheets 폴백: %s", exc)
            _available = False
        return _available


def reset_state():
    """테스트용 — 캐시된 가용성 초기화(NullPool이라 닫을 풀 없음)."""
    global _checked, _available
    with _lock:
        _checked = False
        _available = False


@contextlib.contextmanager
def get_conn(*, autocommit: bool = False):
    """1회용 연결(NullPool) — 매 작업마다 새 연결 후 close. 트랜잭션 풀러 호환."""
    conn = _connect(db_url(), autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()


@contextlib.contextmanager
def tx():
    """트랜잭션 — 블록 정상 종료 시 commit, 예외 시 rollback. (커밋 후에만 성공 응답)"""
    conn = _connect(db_url(), autocommit=False)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextlib.contextmanager
def query():
    """읽기 전용 — autocommit 연결(트랜잭션 안 열어둠). NullPool 1회용."""
    conn = _connect(db_url(), autocommit=True)
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


@contextlib.contextmanager
def direct_conn():
    """마이그레이션용 **직접 연결(5432)** 1회용 — 정상 종료 시 commit, 예외 시 rollback."""
    conn = _connect(direct_url(), autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_ddl(ddl: str):
    """DDL을 **직접 연결(5432)** + autocommit로 실행 — 트랜잭션 풀러의 DDL/prepared 이슈 회피.

    스키마 스크립트는 여러 문장(CREATE EXTENSION/FUNCTION/TRIGGER…) → psycopg3 확장 프로토콜은
    단일 문장만 허용하므로, 각 문장을 개별 실행($$ 함수 본문 경계 보존).
    """
    conn = _connect(direct_url(), autocommit=True)
    try:
        with conn.cursor() as cur:
            for stmt in _split_sql(ddl):
                if stmt.strip():
                    cur.execute(stmt)
    finally:
        conn.close()


def _split_sql(script: str) -> list:
    """세미콜론 기준 문장 분할 — 단, $$…$$ 달러 인용(함수 본문) 안의 ';'는 무시."""
    stmts = []
    buf = []
    i = 0
    n = len(script)
    in_dollar = False
    while i < n:
        ch = script[i]
        if script.startswith("$$", i):
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        if ch == ";" and not in_dollar:
            stmts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


_schema_done = False


def init_schema():
    """이관 스키마를 idempotent 적용(1단계 collect_history·user_tokens, 2단계 market_links). 직접 연결로 실행."""
    global _schema_done
    if _schema_done or not pg_enabled():
        return
    here = Path(__file__).parent
    for fname in ("schema_stage1.sql", "schema_stage2.sql", "schema_stage3.sql"):
        f = here / fname
        if f.exists():
            run_ddl(f.read_text(encoding="utf-8"))
    _schema_done = True
    logger.info("Postgres 이관 스키마 적용 완료(직접 연결)")
