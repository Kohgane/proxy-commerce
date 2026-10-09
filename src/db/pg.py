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
import contextvars
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


def pool_wait_sec() -> float:
    """풀 대여 대기 상한(초) — 기본 5. 라이브러리 기본 30초는 바닥난 풀에서 요청 스레드를 통째로 묶는다(Z8)."""
    try:
        return max(0.5, float(os.getenv("PG_POOL_WAIT_SEC", "5") or 5))
    except ValueError:
        return 5.0


def pool_stats() -> dict:
    """풀 상태(진단·로그용) — 풀이 없으면 빈 dict."""
    try:
        st = _pool.get_stats() if _pool is not None and hasattr(_pool, "get_stats") else {}
        return {k: st.get(k) for k in ("pool_size", "pool_available", "requests_waiting", "requests_errors",
                                       "requests_wait_ms", "connections_num") if k in st}
    except Exception:
        return {}


def _connect(url: str, *, autocommit: bool = False):
    """psycopg3 연결 — NullPool(1회용) + prepared statement 비활성(풀러 호환).

    Z9: 연결을 **여는 시간**(TCP+TLS+인증)은 쿼리 시간(`db`)에 안 들어간다 — `db_connect` 구간으로 따로 잰다.
    01:21 KST 사전검증 25초 중 ~21초가 db·external 어디에도 안 잡혔다(쿼리 12번 = 1회용 연결 12번일 수 있다).
    """
    import time as _t
    import psycopg
    t0 = _t.perf_counter()
    try:
        return psycopg.connect(
            url,
            autocommit=autocommit,
            prepare_threshold=None,   # 트랜잭션 풀러(6543)에서 prepared statement 미사용
            connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "10") or 10),
        )
    finally:
        try:
            from src.utils.perf import _bucket as _get_bucket, perf_add_ms
            dt = (_t.perf_counter() - t0) * 1000.0
            b = _get_bucket()
            if b is not None:
                b["db_connect"] = round(b.get("db_connect", 0.0) + dt, 2)
            perf_add_ms("db_connect", dt)
        except Exception:
            pass


def pg_enabled() -> bool:
    """Postgres 사용 가능 여부 — URL 설정 + psycopg3 임포트 가능 + 최초 접속 성공."""
    global _checked, _available
    if _checked:
        return _available
    # Z8: 이 잠금 안에서 첫 접속(최대 connect_timeout)을 한다 — 5초 넘게 못 잡으면 잠금 없이 같은 확인을 한다
    #   (결과는 같고 캐시만 늦게 찬다 — 기다리느라 요청 스레드가 줄 서지 않게).
    from src.utils.locks import try_lock
    with try_lock(_lock, code="pg_check_lock_timeout", what="DB 가용 확인"):
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


def is_deployed() -> bool:
    """배포(운영) 컨테이너 여부 — Render/컨테이너 마커로 판별.

    로컬 개발/CI는 False. Render는 RENDER 계열 env를 주입한다. APP_ENV=production도 배포로 본다.
    (배포서 휘발 저장을 조용히 돌리는 걸 막기 위한 신호 — v87-W3.) 일반 테스트는 RENDER·production
    미설정이라 자연히 False라 부팅 가드에 걸리지 않는다(가드를 검증하는 테스트만 명시적으로 켠다).
    """
    if str(os.getenv("APP_ENV", "")).strip().lower() in ("ci", "test", "development", "dev", "local"):
        return False
    for k in ("RENDER", "RENDER_SERVICE_ID", "RENDER_INSTANCE_ID"):
        if os.getenv(k):
            return True
    return str(os.getenv("APP_ENV", "")).strip().lower() == "production"


def storage_status() -> dict:
    """수집 이력 등 PG 계층 저장소의 내구성 신호 — /health·부팅 가드·진단이 공유하는 단일 소스.

    durable=True면 재배포에도 레코드 생존(Supabase PG). False면 컨테이너 로컬 in-memory로
    폴백 중 = **배포마다 소실**(v87-W3의 데이터 소실 원인). 삭제/쓰기 없음(순수 조회).
    """
    url_set = bool(db_url())
    try:
        available = pg_enabled()
    except Exception:
        available = False
    deployed = is_deployed()
    return {
        "durable": bool(available),
        "backend": "postgres" if available else "in-memory",
        "url_set": url_set,
        "deployed": deployed,
        # 배포인데 내구 저장이 아니면 = 조용한 휘발(경고 대상).
        "volatile_in_production": bool(deployed and not available),
    }


_pool = None
_pool_checked = False


def _persistent_pool():
    """v51 STEP2: 상시 커넥션 풀(psycopg_pool)을 1회 생성해 재사용 — **기본 ON**(PG_PERSISTENT_POOL=0으로만 끔).

    v49에선 opt-in(기본 OFF)이었으나 v51에서 기본 ON 전환(오너 지시). 워커당 소형 풀(pool_size=5,
    pre_ping, recycle) — 요청마다 TCP+TLS 핸드셰이크를 제거(내비 지연 완화). 트랜잭션 풀러(6543) 호환 위해
    prepared statement 비활성·autocommit 읽기. **풀 라이브러리 미설치·DB URL 없음·생성 실패 시 None**
    (정직 폴백 → 기존 요청범위 1회용 연결, 무회귀). PG_PERSISTENT_POOL=0 이면 강제 OFF.
    """
    global _pool, _pool_checked
    if os.getenv("PG_PERSISTENT_POOL", "1") != "1":   # 기본 ON, =0 으로만 끔
        return None
    if not db_url():                                   # DB 미설정(개발/테스트 인메모리) → 폴백
        return None
    if _pool_checked:
        return _pool
    from src.utils.locks import try_lock
    with try_lock(_lock, code="pg_pool_lock_timeout", what="DB 상시 풀 만들기") as _got:
        if not _got:
            return None                                # 이번 요청은 1회용 연결로(풀은 다른 스레드가 만드는 중)
        if _pool_checked:
            return _pool
        _pool_checked = True
        try:
            from psycopg_pool import ConnectionPool
            _pool = ConnectionPool(
                conninfo=db_url(),
                min_size=int(os.getenv("PG_POOL_MIN", "1") or 1),
                max_size=int(os.getenv("PG_POOL_SIZE", "5") or 5),
                max_idle=float(os.getenv("PG_POOL_RECYCLE", "300") or 300),
                # 풀러 호환 · Z8: 풀이 새로 여는 연결에도 connect_timeout(1회용 `_connect`와 같은 값)
                kwargs={"prepare_threshold": None, "autocommit": True,
                        "connect_timeout": int(os.getenv("PG_CONNECT_TIMEOUT", "10") or 10)},
                timeout=pool_wait_sec(),
                check=ConnectionPool.check_connection,                   # pre_ping
                open=True,
            )
            logger.info("DB 상시 커넥션 풀 활성(psycopg_pool, size=%s)", os.getenv("PG_POOL_SIZE", "5"))
        except Exception as exc:
            logger.warning("상시 풀 생성 실패 — 요청범위 연결 폴백: %s", exc)
            _pool = None
        return _pool


def reset_state():
    """테스트용 — 캐시된 가용성·풀 초기화."""
    global _checked, _available, _pool, _pool_checked
    with _lock:
        _checked = False
        _available = False
        try:
            if _pool is not None:
                _pool.close()
        except Exception:
            pass
        _pool = None
        _pool_checked = False


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
    sc = _job_scope.get()
    if sc is not None:
        held = sc.acquire()
        if held is not None:
            conn, is_new = held
            _perf_mark("db_write", new_conn=is_new)
            try:
                with conn.transaction(), conn.cursor() as cur, _timed_db():
                    yield cur
            finally:
                sc.release()
            return
    _perf_mark("db_write")
    conn = _connect(db_url(), autocommit=False)
    try:
        with conn.cursor() as cur, _timed_db():
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _perf_mark(kind: str, new_conn: bool = True) -> None:
    try:
        from src.utils.perf import perf_count
        perf_count(kind, 1)
        perf_count("db_query", 1)          # v49 STEP2: 요청당 총 쿼리 수(N+1 진단)
        if new_conn:
            perf_count("db_conn", 1)
    except Exception:
        pass


@contextlib.contextmanager
def _timed_db():
    """v49 STEP2: 이 DB 작업(execute+fetch)의 경과 ms를 'db' 버킷 합산 + 개별 ms 리스트에 기록.

    query()/tx() 안에서 cursor yield 구간을 감싸므로 호출부의 실제 쿼리 시간이 측정된다.
    """
    import time as _t
    t0 = _t.perf_counter()
    try:
        yield
    finally:
        dt = (_t.perf_counter() - t0) * 1000.0
        try:
            from src.utils.perf import perf_block as _pb, perf_add_ms
            # perf_block과 동일 버킷('db')에 합산(뷰 레벨 중복 래핑 제거로 이중계상 없음).
            b = None
            from src.utils.perf import _bucket as _get_bucket  # type: ignore
            b = _get_bucket()
            if b is not None:
                b["db"] = round(b.get("db", 0.0) + dt, 2)
            perf_add_ms("db", dt)
        except Exception:
            pass


def _request_read_conn():
    """요청(request) 범위 내 읽기 연결을 1개로 재사용한다 — 페이지당 연결 핸드셰이크를 N→1로.

    속도 핵심(오너): query()가 매번 새 연결을 열어 수집이력 3연결(64ms)·드로어 6연결(386ms)이
    걸렸다. 요청 동안 autocommit 읽기 연결 하나를 flask.g에 캐시해 재사용하고 teardown에서 닫는다.
    요청 컨텍스트가 아니면 None(호출부가 1회용 연결 사용).
    """
    try:
        from flask import g, has_request_context
        if not has_request_context():
            return None, False
        # Z8(오너 2026-10-08 23:3x 워커 교착): 요청 컨텍스트를 **복사한** 스레드(사전검증 잡 `_pv_job`·마켓별 future)도
        #   has_request_context()가 참이다. 그 스레드가 요청이 끝난 뒤(teardown이 이미 반납한 뒤) 여기서 풀 연결을 빌려
        #   g에 걸면 **아무도 반납하지 않는다** — 잡 1회에 1개씩 새어 풀(5)이 바닥나면 그 워커의 모든 요청이
        #   getconn에서 기다린다. 요청을 받은 그 스레드만 g 연결을 쓰고, 나머지는 1회용(쓰고 바로 닫음).
        owner = getattr(g, "_kgp_req_thread", None)
        if owner is None:
            owner = threading.get_ident()
            setattr(g, "_kgp_req_thread", owner)
        if owner != threading.get_ident():
            return None, False
        c = getattr(g, "_kgp_db_read_conn", None)
        if c is not None and not getattr(c, "closed", False):
            return c, False                     # 재사용(새 연결 아님)
        # v49 STEP2: 상시 풀이 켜져 있으면 풀에서 대여(핸드셰이크 없음) — 없으면 1회용 연결.
        pool = _persistent_pool()
        if pool is not None:
            try:
                # Z8: 풀이 바닥났을 때 30초(라이브러리 기본)씩 기다리지 않는다 — 5초 뒤 사유를 남기고 1회용으로.
                c = pool.getconn(timeout=pool_wait_sec())
                try:
                    c.autocommit = True
                except Exception:
                    pass
                setattr(g, "_kgp_db_read_conn", c)
                setattr(g, "_kgp_db_conn_pooled", True)
                return c, False                 # 풀 대여 = 새 핸드셰이크 아님(연결 수 미계상)
            except Exception as exc:
                logger.warning("[DB] pg_pool_timeout — 풀 대여 %ss 안에 실패(%s: %s) · 풀 %s → 1회용 연결",
                               pool_wait_sec(), type(exc).__name__, str(exc)[:120], pool_stats())
        c = _connect(db_url(), autocommit=True)
        setattr(g, "_kgp_db_read_conn", c)
        setattr(g, "_kgp_db_conn_pooled", False)
        return c, True                          # 이 요청의 첫 읽기 연결(새로 열림)
    except Exception:
        return None, False


def close_request_conn(_exc=None):
    """요청 종료 시 캐시된 읽기 연결을 닫는다(app.teardown_request에 등록)."""
    try:
        from flask import g
        c = getattr(g, "_kgp_db_read_conn", None)
        if c is not None:
            pooled = getattr(g, "_kgp_db_conn_pooled", False)
            try:
                if pooled and _pool is not None:
                    _pool.putconn(c)            # v49 STEP2: 풀에 반납(닫지 않음)
                else:
                    c.close()
            except Exception:
                pass
            setattr(g, "_kgp_db_read_conn", None)
            setattr(g, "_kgp_db_conn_pooled", False)
    except Exception:
        pass


class _JobConn:
    """잡 하나가 쓰는 DB 연결 1개 — 처음 쓸 때 열고(1회용 `_connect`, 요청 풀 아님) 잡이 끝나면 닫는다.

    Z9 후속(오너 2026-10-09 13:31 KST 실측): 사전검증 잡 한 번에 연결을 19번 열었다(회당 ~20ms, 합 385ms —
    `db_connect`). 잡 상태 갱신(`_pv_update` = 읽기 1 + 쓰기 1)·자격 읽기·규칙 읽기가 쿼리마다 1회용이었다.

    - **요청 풀과 섞지 않는다**(Z9에서 되돌린 것 — 백그라운드가 풀(5)을 쥐면 요청이 굶는다).
    - 잡 스레드와 마켓별 스레드(`copy_context`로 물려받음)가 **한 연결을 차례로** 쓴다 — 블록(쿼리·트랜잭션) 하나씩
      잠금. 남이 오래 쥐고 있으면(`PG_JOB_CONN_WAIT_SEC`, 기본 2초) 기다리지 않고 1회용으로(지금과 같음 — 더 나빠지지 않음).
    - 같은 스레드가 블록 안에서 또 부르면(트랜잭션 안의 읽기 등) 1회용 — 예전 의미(따로 커밋된 연결) 그대로.
    - 잡이 끝난 뒤에도 물려받은 스레드(마감 넘긴 마켓 스레드·백그라운드 판정)가 부르면 1회용. 쓰는 중에 잡이 끝나면
      **그 블록이 끝날 때** 닫는다(남의 쿼리 도중에 닫지 않는다).
    - 연결이 깨졌으면(`broken`/`closed`) 새로 연다.
    """

    def __init__(self):
        self._cv = threading.Condition()
        self._busy = False
        self._holder = None
        self._conn = None
        self._done = False
        self.opened = 0

    def acquire(self):
        """(연결, 새로 열었나) — 못 쓰면 None(호출부가 1회용 연결)."""
        me = threading.get_ident()
        with self._cv:
            if self._done or self._holder == me:
                return None
            if not self._cv.wait_for(lambda: self._done or not self._busy, timeout=job_conn_wait_sec()):
                logger.info("[DB] job_conn_busy — %ss 안에 잡 연결이 비지 않아 1회용 연결", job_conn_wait_sec())
                return None
            if self._done:
                return None
            self._busy, self._holder = True, me
            c = self._conn
        try:
            is_new = False
            if c is None or getattr(c, "closed", False) or getattr(c, "broken", False):
                if c is not None:
                    try:
                        c.close()
                    except Exception:
                        pass
                c = _connect(db_url(), autocommit=True)
                is_new = True
                with self._cv:
                    self._conn = c
                    self.opened += 1
            return c, is_new
        except Exception:
            with self._cv:
                self._conn = None
            self.release()
            raise

    def release(self):
        with self._cv:
            self._busy, self._holder = False, None
            if self._done:
                self._close()
            self._cv.notify()

    def _close(self):
        c, self._conn = self._conn, None
        if c is not None:
            try:
                c.close()
            except Exception:
                pass

    def finish(self):
        """잡 끝 — 비어 있으면 지금 닫고, 누가 쓰는 중이면 그 블록 끝(`release`)에서 닫는다."""
        with self._cv:
            self._done = True
            if not self._busy:
                self._close()
            self._cv.notify_all()


_job_scope = contextvars.ContextVar("kgp_pg_job_conn", default=None)


def job_conn_wait_sec() -> float:
    try:
        return max(0.1, float(os.getenv("PG_JOB_CONN_WAIT_SEC", "2") or 2))
    except (TypeError, ValueError):
        return 2.0


@contextlib.contextmanager
def job_conn():
    """잡(백그라운드 작업) 범위 — 안에서 부르는 query()/tx()가 연결 1개를 함께 쓴다. 끝나면 닫는다.

    `with pg.job_conn():` 안에서 `copy_context()`로 띄운 스레드도 같은 연결을 쓴다(차례로).
    PG가 꺼져 있거나 이미 바깥 범위가 있으면 아무것도 안 한다(바깥 범위를 그대로 쓴다).
    """
    if _job_scope.get() is not None:
        yield _job_scope.get()
        return
    sc = _JobConn()
    token = _job_scope.set(sc)
    try:
        yield sc
    finally:
        _job_scope.reset(token)
        sc.finish()


@contextlib.contextmanager
def query():
    """읽기 전용 — 요청 스레드는 요청 연결 1개를 재사용, 그 밖(잡·마켓별 스레드·백그라운드)은 1회용.

    Z9: 잡 스레드도 상시 풀에서 빌려 보려 했으나(연결 여는 시간을 줄이려고) **되돌렸다** — 백그라운드 스레드가
    쿼리 블록을 오래 쥐면 요청 스레드와 같은 풀(5)을 나눠 써 요청이 `pg_pool_timeout` 5초씩 기다렸다(gunicorn 2워커 실측
    대시보드 5.0초, main은 수 ms). 1회용 연결의 비용은 `db_connect` 구간으로 잰다 — 운영 수치를 보고 정한다.
    """
    conn, is_new = _request_read_conn()
    if conn is not None:
        _perf_mark("db_read", new_conn=is_new)
        with conn.cursor() as cur, _timed_db():
            yield cur
        return
    sc = _job_scope.get()
    if sc is not None:
        held = sc.acquire()
        if held is not None:
            conn, is_new = held
            _perf_mark("db_read", new_conn=is_new)
            try:
                with conn.cursor() as cur, _timed_db():
                    yield cur
            finally:
                sc.release()
            return
    _perf_mark("db_read", new_conn=True)
    conn = _connect(db_url(), autocommit=True)
    try:
        with conn.cursor() as cur, _timed_db():
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
    # v87-S3: stage4 = settings(가격 정책). 스키마 파일은 순서대로 idempotent 적용된다.
    for fname in ("schema_stage1.sql", "schema_stage2.sql", "schema_stage3.sql", "schema_stage4.sql",
                  "schema_stage5.sql",   # v88-B: translation_jobs(백그라운드 번역 큐)
                  "schema_stage6.sql",   # P4: market_registrations(마켓 등록 대장·반려감시 소스)
                  "schema_stage7.sql",   # C-F17-B: telegram_links(폰 기본 입구의 chat_id↔셀러 바인딩)
                  "schema_stage8.sql",   # C-F19: user_identities((provider,email)→user_id) + 병합 백업
                  "schema_stage9.sql",   # D1: image_translate_usage(장당 과금 장부) + image_bench_runs
                  "schema_stage10.sql",  # F24: sourcing_rules(소싱 원칙) + 봇별 기본 등록 계정
                  "schema_stage11.sql",  # F25b: api_rate_slots(서버 전역 호출 차례표)
                  "schema_stage12.sql",  # D2: image_ko_blobs(번역본 바이트 — 로컬 파일 폐기)
                  "schema_stage13.sql",  # D2b: 번역본의 외부 주소(cdn_url) — 마켓이 가져갈 수 있게
                  "schema_stage14.sql",  # D3-8: 이미지 번역 자동 큐 + 전역 작은 상태(app_state)
                  "schema_stage15.sql",  # AUTH-1: 이메일+비밀번호 계정(password_accounts) — 시트 대신 커밋 확인
                  "schema_stage16.sql"): # J1: 옵션 값·상품명 번역기 큐(수집하면 자동)
        f = here / fname
        if f.exists():
            run_ddl(f.read_text(encoding="utf-8"))
    _schema_done = True
    logger.info("Postgres 이관 스키마 적용 완료(직접 연결)")
