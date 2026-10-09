"""Z9 후속(오너 2026-10-09 13:31 KST 실측) — 사전검증 잡이 DB 연결 1개를 끝까지 함께 쓴다.

증거: `[PV] job=e58ea897 … perf={db:78.3, db_connect:384.9 · db_query:19, db_conn:19}` — 쿼리마다 1회용 연결
(회당 ~20ms). 잡 상태 갱신(`_pv_update` = 읽기 1 + 쓰기 1)·자격 읽기·규칙 읽기가 각자 연결을 열었다.

계약
- `pg.job_conn()` 안의 query()/tx()는 연결 1개 — 처음 쓸 때 열고 범위가 끝나면 닫는다.
- 요청 풀(`_pool`)은 건드리지 않는다(Z9에서 되돌린 것 — 백그라운드가 풀을 쥐면 요청이 굶는다).
- 마켓별 스레드(`copy_context`)도 같은 연결을 **차례로** 쓴다. 남이 오래 쥐면 기다리지 않고 1회용.
- 같은 스레드가 블록 안에서 또 부르면 1회용(트랜잭션 안의 읽기가 예전처럼 따로 커밋된 연결을 본다).
- 범위가 끝난 뒤 물려받은 스레드는 1회용. 남이 쓰는 중에 끝나면 그 블록 끝에서 닫는다.
- 깨진 연결은 새로 연다. 트랜잭션 예외는 롤백되고 연결은 다음 블록에 그대로 쓴다.
PG 실측(잡 1회 = 연결 1)은 `test_z9b_job_conn_pg.py`(pg-suite 레인).
"""
from __future__ import annotations

import contextlib
import contextvars
import threading
import time

import pytest


class _Cur:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        if self.conn.closed:
            raise RuntimeError("closed connection used")
        self.conn.active += 1
        return self

    def __exit__(self, *a):
        self.conn.active -= 1
        return False

    def execute(self, sql, *a):
        self.conn.log.append(sql)


class _Conn:
    def __init__(self, n, autocommit):
        self.n, self.autocommit = n, autocommit
        self.closed = False
        self.broken = False
        self.active = 0
        self.log = []
        self.tx = []

    def cursor(self):
        return _Cur(self)

    @contextlib.contextmanager
    def transaction(self):
        self.tx.append("begin")
        try:
            yield
        except BaseException:
            self.tx.append("rollback")
            raise
        self.tx.append("commit")

    def commit(self):
        self.tx.append("commit")

    def rollback(self):
        self.tx.append("rollback")

    def close(self):
        assert self.active == 0, "남의 쿼리 도중에 닫음"
        self.closed = True


@pytest.fixture
def fake(monkeypatch):
    from src.db import pg
    opened = []

    def connect(url, *, autocommit=False):
        c = _Conn(len(opened) + 1, autocommit)
        opened.append(c)
        return c

    monkeypatch.setattr(pg, "_connect", connect)
    monkeypatch.setattr(pg, "db_url", lambda: "postgresql://fake")
    # 요청 연결 경로는 이 계약 밖 — 앞 테스트가 남긴 요청 컨텍스트가 있어도 잡 범위만 보게(잡이 요청 풀을 안 빌리는 건 PG 레인 실측)
    monkeypatch.setattr(pg, "_request_read_conn", lambda: (None, False))
    return pg, opened


def test_one_connection_for_reads_and_writes_then_closed(fake):
    pg, opened = fake
    with pg.job_conn() as sc:
        for _ in range(5):
            with pg.query() as cur:
                cur.execute("select")
            with pg.tx() as cur:
                cur.execute("upsert")
        assert len(opened) == 1 and sc.opened == 1
        assert not opened[0].closed
        assert opened[0].tx.count("commit") == 5                    # 쓰기마다 커밋(블록 끝)
    assert opened[0].closed                                         # 범위 끝 = 닫음
    assert opened[0].autocommit is True                             # 읽기는 autocommit, 쓰기는 명시 트랜잭션


def test_without_scope_still_one_shot(fake):
    pg, opened = fake
    for _ in range(3):
        with pg.query() as cur:
            cur.execute("select")
    assert len(opened) == 3 and all(c.closed for c in opened)       # 잡 밖(요청 외)은 예전 그대로


def test_market_threads_inherit_and_take_turns(fake):
    """마켓별 스레드는 `copy_context`로 범위를 물려받는다 — 한 연결을 차례로(동시에 두 블록 X)."""
    import concurrent.futures as cf
    pg, opened = fake
    overlap = []

    def market(i):
        for _ in range(10):
            with pg.query() as cur:
                if cur.conn.active > 1:
                    overlap.append(i)
                cur.execute(f"m{i}")
                time.sleep(0.001)

    with pg.job_conn():
        ex = cf.ThreadPoolExecutor(max_workers=4)
        futs = [ex.submit(contextvars.copy_context().run, market, i) for i in range(4)]
        for f in futs:
            f.result(timeout=10)
        ex.shutdown()
    assert len(opened) == 1 and not overlap
    assert len(opened[0].log) == 40


def test_nested_use_in_same_thread_is_one_shot(fake):
    """트랜잭션 안의 읽기 — 예전처럼 따로 커밋된 연결(같은 연결이면 미커밋 쓰기를 보게 된다)."""
    pg, opened = fake
    with pg.job_conn():
        with pg.tx() as cur:
            cur.execute("upsert")
            with pg.query() as cur2:
                cur2.execute("select")
                assert cur2.conn is not cur.conn
    assert len(opened) == 2 and all(c.closed for c in opened)


def test_busy_too_long_falls_back_to_one_shot(fake, monkeypatch):
    pg, opened = fake
    monkeypatch.setenv("PG_JOB_CONN_WAIT_SEC", "0.2")
    hold, release = threading.Event(), threading.Event()
    got = {}

    def slow_holder():
        with pg.query() as cur:
            cur.execute("long")
            hold.set()
            release.wait(5)

    with pg.job_conn():
        t = threading.Thread(target=contextvars.copy_context().run, args=(slow_holder,))
        t.start()
        hold.wait(5)
        t0 = time.monotonic()
        with pg.query() as cur:
            got["conn"] = cur.conn
        got["waited"] = time.monotonic() - t0
        release.set()
        t.join(5)
    assert got["conn"] is not opened[0] and got["conn"].closed       # 1회용으로 갔다
    assert got["waited"] < 1.5                                       # 무한 대기 없음


def test_scope_end_waits_for_running_block_then_closes(fake):
    """마감 넘긴 마켓 스레드가 쿼리 중일 때 잡이 끝나면 — 그 블록이 끝날 때 닫는다(도중에 닫지 않는다)."""
    pg, opened = fake
    inside, go = threading.Event(), threading.Event()
    after = {}

    def late_market():
        with pg.query() as cur:
            inside.set()
            go.wait(5)
            cur.execute("late")
        with pg.query() as cur:                                     # 잡이 끝난 뒤 = 1회용
            after["conn"] = cur.conn

    with pg.job_conn():
        t = threading.Thread(target=contextvars.copy_context().run, args=(late_market,))
        t.start()
        inside.wait(5)
    assert len(opened) == 1 and not opened[0].closed                 # 쓰는 중 — 아직 안 닫음
    go.set()
    t.join(5)
    assert opened[0].closed                                          # 그 블록 끝에서 닫음
    assert after["conn"] is not opened[0] and after["conn"].closed


def test_broken_connection_is_reopened(fake):
    pg, opened = fake
    with pg.job_conn():
        with pg.query() as cur:
            cur.execute("a")
        opened[0].broken = True
        with pg.query() as cur:
            cur.execute("b")
    assert len(opened) == 2 and all(c.closed for c in opened)


def test_tx_error_rolls_back_and_connection_stays(fake):
    pg, opened = fake
    with pg.job_conn():
        with pytest.raises(ValueError):
            with pg.tx() as cur:
                cur.execute("bad")
                raise ValueError("x")
        with pg.tx() as cur:
            cur.execute("good")
    assert len(opened) == 1
    assert opened[0].tx == ["begin", "rollback", "begin", "commit"]


def test_prevalidate_job_runs_inside_the_scope(monkeypatch):
    """잡 본문(마켓별 스레드 포함)이 범위 안에서 돈다. 잡 줄 db_conn=1(첫 읽기 전에 계측 시작)은 PG 레인 실측."""
    import src.seller_console.views as V
    seen = []

    class Disp:
        def prevalidate(self, product, markets):
            from src.db import pg
            seen.append(pg._job_scope.get())
            return [type("R", (), {"market": m, "ok": True, "error_code": "", "message": "통과", "hint": "",
                                   "reach_ok": None, "reach_ms": None, "reach_detail": "", "details": [],
                                   "action_url": "", "action_label": "", "hold": False, "fixes": [],
                                   "rep_pending": False})() for m in markets]

    monkeypatch.setattr(V, "_PV_MARKET_TIMEOUT_SEC", 1.0)
    monkeypatch.setattr(V, "_PV_JOB_DEADLINE_SEC", 6.0)
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    monkeypatch.setattr(V, "_account_codes_forbidden", lambda m: None)
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: Disp())
    from tests._pv_helper import prevalidate as _pv
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="z9b-seller")
    with app.app_context():
        d = _pv(c, {"product": {"title": "플리츠 세트"}, "markets": ["coupang", "smartstore"]})
    assert d.get("state") == "done", d
    assert len(seen) == 2 and seen[0] is not None and seen[0] is seen[1]   # 두 마켓 스레드 = 같은 잡 범위
