"""Z8(오너 2026-10-08 23:3x KST) — 워커 교착.

실측(오너): GET / 3회 중 2회 60s 무응답·1회 0.9s · /seller/login 무응답 · /pricing 0.8s → 워커 2개 중 1개의
gthread 4개가 전부 묶였다. 코드에서 찾은 근원(재현): 사전검증 잡처럼 **요청 컨텍스트를 복사한 스레드**가
요청이 끝난 뒤 `pg.query()`로 상시 풀 연결을 빌려 g에 걸고 아무도 반납하지 않았다 — 잡 1회에 1개씩, 풀(5)이
바닥나면 그 워커의 모든 요청이 getconn에서 30초(라이브러리 기본)씩 기다린다.
"""
from __future__ import annotations

import contextvars
import json
import logging
import socket
import threading
import time

import pytest


# ── 1. DB 풀 누수 ────────────────────────────────────────────────────────────

class _Cur:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a):
        pass


class _Conn:
    closed = False
    autocommit = False

    def cursor(self):
        return _Cur()

    def close(self):
        self.closed = True


class _Pool:
    def __init__(self, exhausted=False):
        self.out, self.exhausted, self.timeouts = 0, exhausted, []

    def getconn(self, timeout=None):
        self.timeouts.append(timeout)
        if self.exhausted:
            raise TimeoutError("couldn't get a connection after %s sec" % timeout)
        self.out += 1
        return _Conn()

    def putconn(self, c):
        self.out -= 1


@pytest.fixture
def pg_pool(monkeypatch):
    from src.db import pg
    pool = _Pool()
    monkeypatch.setattr(pg, "_persistent_pool", lambda: pool)
    monkeypatch.setattr(pg, "_pool", pool)
    monkeypatch.setattr(pg, "_connect", lambda url, autocommit=False: _Conn())
    monkeypatch.setattr(pg, "db_url", lambda: "postgresql://x")
    return pool


def _app():
    from flask import Flask
    from src.db import pg
    from src.utils import stall_guard
    app = Flask(__name__)
    stall_guard.install(app)
    app.teardown_request(pg.close_request_conn)
    return app


def test_copied_context_job_does_not_leak_pool_connections(pg_pool):
    """사전검증 잡과 같은 모양 — 요청이 202로 끝난 뒤 복사된 컨텍스트 스레드가 query(). 5회 돌려도 빌린 채 0."""
    from src.db import pg
    app = _app()
    for _ in range(5):
        with app.test_request_context("/seller/collect/prevalidate"):
            app.preprocess_request()
            with pg.query():
                pass
            ctx = contextvars.copy_context()
            app.do_teardown_request()

        def job():
            with pg.query():
                pass
        t = threading.Thread(target=ctx.run, args=(job,))
        t.start()
        t.join()
    assert pg_pool.out == 0


def test_job_thread_first_query_also_does_not_take_ownership(pg_pool):
    """요청 스레드가 query를 한 번도 안 불렀어도(before_request가 주인을 표시) 잡 스레드는 1회용 연결."""
    from src.db import pg
    app = _app()
    with app.test_request_context("/x"):
        app.preprocess_request()
        ctx = contextvars.copy_context()
        app.do_teardown_request()

    def job():
        with pg.query():
            pass
    t = threading.Thread(target=ctx.run, args=(job,))
    t.start()
    t.join()
    assert pg_pool.out == 0 and pg_pool.timeouts == []


def test_exhausted_pool_waits_5s_not_30s_then_falls_back(monkeypatch, pg_pool, caplog):
    from src.db import pg
    pg_pool.exhausted = True
    app = _app()
    with caplog.at_level(logging.WARNING, logger="src.db.pg"):
        with app.test_request_context("/"):
            app.preprocess_request()
            with pg.query():
                pass
            app.do_teardown_request()
    assert pg_pool.timeouts == [5.0]
    assert "pg_pool_timeout" in caplog.text


# ── 2. 외부 호출 타임아웃 (connect 5 · read 15) ─────────────────────────────

def test_clamp_defaults_and_caps():
    from src.utils.http_timeouts import clamp
    assert clamp(None) == (5.0, 15.0)
    assert clamp(30) == (5.0, 15.0)
    assert clamp(3) == (3.0, 3.0)
    assert clamp((10, 60)) == (5.0, 15.0)
    assert clamp((2, None)) == (2.0, 15.0)


def test_allow_raises_read_cap_only_inside_block_and_thread():
    from src.utils.http_timeouts import allow, clamp
    with allow(read=60, why="테스트"):
        assert clamp(60) == (5.0, 60.0)
        seen = {}
        t = threading.Thread(target=lambda: seen.update(c=clamp(60)))
        t.start()
        t.join()
        assert seen["c"] == (5.0, 15.0)                       # 다른 스레드는 그대로
    assert clamp(60) == (5.0, 15.0)


@pytest.fixture
def hang_server():
    """연결은 받고 응답은 영영 안 주는 서버."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    conns = []
    stop = threading.Event()

    def loop():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                c, _ = srv.accept()
                conns.append(c)
            except OSError:
                pass
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d/" % srv.getsockname()[1]
    stop.set()
    for c in conns:
        c.close()
    srv.close()


def test_hanging_upstream_returns_within_15s_even_without_timeout(hang_server):
    """호출부가 타임아웃을 안 줘도(=예전엔 영원히) 15초 안에 ReadTimeout으로 돌아온다."""
    import requests
    from src.utils import http_timeouts
    http_timeouts.install()
    t0 = time.monotonic()
    with pytest.raises(requests.exceptions.ReadTimeout):
        requests.get(hang_server)
    assert time.monotonic() - t0 < 16.0


def test_hanging_upstream_long_caller_timeout_is_capped(monkeypatch, hang_server):
    """호출부가 60s를 줘도 상한에서 끊긴다(상한을 2s로 낮춰 빠르게 확인)."""
    import requests
    from src.utils import http_timeouts
    http_timeouts.install()
    monkeypatch.setenv("HTTP_READ_TIMEOUT_MAX", "2")
    t0 = time.monotonic()
    with pytest.raises(requests.exceptions.ReadTimeout):
        requests.get(hang_server, timeout=60)
    assert time.monotonic() - t0 < 4.0


def test_app_installs_the_guard():
    import src.order_webhook  # noqa: F401
    from requests.adapters import HTTPAdapter
    assert getattr(HTTPAdapter.send, "__kgp_timeout_guard__", False) is True


# ── 3. 잠금 — acquire(timeout=5) + 사유코드로 통과 ─────────────────────────

def test_try_lock_gives_up_with_reason(caplog):
    from src.utils.locks import try_lock, wait_sec
    assert wait_sec() == 5.0
    lk = threading.Lock()
    lk.acquire()
    t0 = time.monotonic()
    with caplog.at_level(logging.WARNING, logger="src.utils.locks"):
        with try_lock(lk, code="demo_busy", what="데모", timeout=0.2) as got:
            assert got is False
    assert time.monotonic() - t0 < 1.0 and "demo_busy" in caplog.text
    lk.release()
    with try_lock(lk, code="x", timeout=0.2) as got:
        assert got is True and lk.locked()
    assert not lk.locked()


def test_ocr_busy_returns_unavailable_instead_of_waiting(monkeypatch):
    """대표 사진 OCR 줄(동시 1개)이 막혀 있으면 기다리지 않고 「판정 못 함」 — 사전검증을 막지 않는다."""
    from src.services import coupang_image_check as C
    monkeypatch.setenv("LOCK_WAIT_SEC", "0.2")
    C._OCR_SEM.acquire()
    try:
        t0 = time.monotonic()
        assert C._read_text(b"x") == (None, "")
        assert time.monotonic() - t0 < 1.0
    finally:
        C._OCR_SEM.release()


# ── 4. 네이버 카테고리 트리 — 요청 밖 ───────────────────────────────────────

@pytest.fixture
def ncat(monkeypatch):
    from src.uploaders import naver_categories as NC
    from src.db import image_translate_queue_pg as ST
    NC.reset()
    ST.state_set(NC.STATE_KEY, {})
    monkeypatch.setattr(NC, "BACKGROUND", True)
    yield NC
    NC.reset()
    ST.state_set(NC.STATE_KEY, {})


def test_tree_never_fetches_in_caller_thread(monkeypatch, ncat):
    """트리가 없을 때 tree()는 기다리지 않는다 — 받기는 백그라운드 스레드(동시 1개)에서."""
    calls, gate = [], threading.Event()

    def slow_fetch(account=""):
        calls.append(threading.current_thread().name)
        gate.wait(5)
        return [{"id": "1", "name": "투피스", "wholeCategoryName": "패션의류>여성의류>투피스", "last": True}]
    monkeypatch.setattr(ncat, "_fetch", slow_fetch)
    t0 = time.monotonic()
    assert ncat.tree() is None and ncat.tree() is None
    assert time.monotonic() - t0 < 0.5
    assert ncat.leaf_state("1") == "unknown"                  # 트리 미수신 → 리프 검사 생략
    gate.set()
    ncat._REFRESH["thread"].join(5)
    assert calls == ["naver-category-tree"]                   # 두 번 불렀어도 받기는 한 번
    assert ncat.leaf_state("1") == "leaf"


def test_failed_fetch_retries_on_a_later_request(monkeypatch, ncat):
    monkeypatch.setattr(ncat, "_fetch", lambda account="": None)
    ncat.tree()
    ncat._REFRESH["thread"].join(5)
    assert ncat.start_background_refresh() is False           # 실패 직후 RETRY_SEC 동안은 다시 안 띄움
    monkeypatch.setattr(ncat, "RETRY_SEC", 0.0)
    assert ncat.start_background_refresh() is True


def test_prevalidate_passes_with_tree_missing(monkeypatch, ncat):
    """트리를 못 받은 상태 — 오너 지정 리프면 리프 검사 없이 사전검증 통과(네이버가 답한다)."""
    monkeypatch.setattr(ncat, "_fetch", lambda account="": None)
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import smartstore_routing as SR
    import contextlib
    import urllib.request
    monkeypatch.setattr(UD, "smartstore_approved", lambda store="": True)
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    pd = {"title_ko": "플리츠 미니멀 여성 여름 세트", "naver_category_id": "50000805", "price": 168, "currency": "CNY",
          "images": ["https://img.alicdn.com/a.jpg"], "item_id": "z8-1"}
    t0 = time.monotonic()
    r = UD.UploadDispatcher()._prevalidate_market(pd, "smartstore")
    assert r.ok, r
    assert time.monotonic() - t0 < 3.0


# ── 5. 감시 — 30초 넘는 요청의 스택 덤프 ────────────────────────────────────

def test_stall_guard_dumps_stack_of_slow_request(caplog):
    from src.utils import stall_guard as S
    S.reset()
    ready, release = threading.Event(), threading.Event()

    def stuck_in_here():
        S.begin("/seller/login")
        ready.set()
        release.wait(5)
        S.end()
    t = threading.Thread(target=stuck_in_here)
    t.start()
    ready.wait(2)
    with caplog.at_level(logging.ERROR, logger="src.utils.stall_guard"):
        lines = S.check_once(now=time.monotonic() + 31)
        again = S.check_once(now=time.monotonic() + 32)       # 같은 표시(30s)는 한 번만
    release.set()
    t.join()
    assert len(lines) == 1 and again == []
    assert "path=/seller/login" in lines[0] and "stuck_in_here" in lines[0]
    assert "[STALL]" in caplog.text


# ── 6. 로그 비밀값 마스킹 ───────────────────────────────────────────────────

def test_request_log_masks_secret_headers(caplog):
    from flask import Flask
    from src.middleware.request_logger import RequestLogger
    app = Flask(__name__)
    RequestLogger(app)

    @app.post("/cron/reprice")
    def _r():
        return "ok"
    secrets = {"X-Cron-Secret": "cron-SECRET-1", "Authorization": "Bearer tok-SECRET-2", "Cookie": "session=SECRET-3",
               "X-Api-Key": "api-SECRET-4", "X-Dashboard-Key": "dash-SECRET-5", "X-KGP-Relay-Key": "relay-SECRET-6"}
    with caplog.at_level(logging.DEBUG, logger="proxy_commerce.request"):
        app.test_client().post("/cron/reprice", headers=dict(secrets, **{"User-Agent": "cron-job.org"}))
    text = caplog.text
    assert "request_headers" in text or "cron-job.org" in text
    for v in secrets.values():
        assert v not in text, v
    assert "SECRET" not in text
    assert "cron-job.org" in text                                # 비밀 아닌 헤더는 그대로


# ── 7. 크론 — 요청 스레드를 붙잡지 않는다 ────────────────────────────────────

def test_cron_returns_202_fast_and_409_while_running(monkeypatch):
    from flask import Flask
    from src.pricing.cron import cron_bp
    from src.utils import bg_job
    bg_job.reset()
    monkeypatch.delenv("CRON_SECRET", raising=False)
    app = Flask(__name__)
    app.register_blueprint(cron_bp)
    gate = threading.Event()
    monkeypatch.setattr("src.pricing.engine.PricingEngine.evaluate", lambda self, dry_run=None: gate.wait(5) and {"evaluated": 1})
    monkeypatch.setattr("src.pricing.cron._send_summary_notification", lambda r: None)
    c = app.test_client()
    t0 = time.monotonic()
    r1 = c.post("/cron/reprice")
    assert r1.status_code == 202 and time.monotonic() - t0 < 1.0
    r2 = c.post("/cron/reprice")
    assert r2.status_code == 409 and r2.get_json()["error"] == "진행 중"
    gate.set()
    st = bg_job.join("reprice")
    assert st["state"] == "done" and st["elapsed_ms"] is not None
    assert c.post("/cron/reprice").status_code == 202                 # 끝나면 다시 받는다
    bg_job.join("reprice")
