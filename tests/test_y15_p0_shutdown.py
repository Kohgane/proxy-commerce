"""Y15 P0-운영(오너 2026-10-23 Render 로그) — 배포 뒤 인스턴스 먹통 재발 방지.

vssjj: 「Handling signal: term → Worker exiting → Shutting down: Master」 뒤에도 프로세스가 살아(09:33 틱 감시 경고) 포트는 닫힌 채
트래픽을 받았다. 로컬 재현 = 마스터 안 스레드 풀 일 하나로 마스터가 SIGTERM 뒤 20초+ 생존.
"""
import os
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import time
import urllib.request

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUNICORN = shutil.which("gunicorn")
needs_gunicorn = pytest.mark.skipif(not GUNICORN, reason="gunicorn 없음")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(**extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("DATABASE_URL", "SUPABASE_DB_URL", "PYTEST", "KGP_DEFER"))}
    env.update({"PYTHONPATH": REPO, "SMARTSTORE_LIVE_PROBE": "0", "TICK_GAP_WATCH": "1", "APP_ENV": "development"})
    env.update(extra)
    return env


def _boot_and_term(app_spec, cwd, env, boot_sec=40.0):
    port = _free_port()
    p = subprocess.Popen([GUNICORN, app_spec, "--config", os.path.join(REPO, "gunicorn.conf.py"),
                          "--bind", f"127.0.0.1:{port}"], cwd=cwd, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        t0 = time.monotonic()
        while time.monotonic() - t0 < boot_sec:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1).read()
                break
            except Exception:
                if p.poll() is not None:
                    pytest.fail("gunicorn이 뜨지 못함:\n" + p.stdout.read().decode(errors="ignore")[-2000:])
                time.sleep(0.2)
        else:
            pytest.fail("포트가 안 열림")
        bind_sec = time.monotonic() - t0
        t1 = time.monotonic()
        p.send_signal(signal.SIGTERM)
        try:
            p.wait(timeout=5)                                   # 상한 5초
        except subprocess.TimeoutExpired:
            p.kill()
            pytest.fail("SIGTERM 뒤 5초 안에 프로세스가 안 끝남:\n" + p.stdout.read().decode(errors="ignore")[-2000:])
        return bind_sec, time.monotonic() - t1, p.stdout.read().decode(errors="ignore")
    finally:
        if p.poll() is None:
            p.kill()


@needs_gunicorn
def test_real_app_exits_within_3s_after_sigterm():
    _bind, took, log = _boot_and_term("src.order_webhook:app", REPO, _env())
    assert took < 3.0, (took, log[-1500:])
    assert "Shutting down: Master" in log


@needs_gunicorn
def test_stuck_pool_work_in_master_cannot_keep_process_alive(tmp_path):
    """그날의 모양 — 마스터 안 데몬 스레드가 스레드 풀에 긴 일을 맡겨 둔 채 SIGTERM. 강제 종료가 잡아야 한다."""
    (tmp_path / "stuckapp.py").write_text(textwrap.dedent("""
        import threading, time
        from concurrent.futures import ThreadPoolExecutor
        _pool = ThreadPoolExecutor(max_workers=1)
        threading.Thread(target=lambda: _pool.submit(time.sleep, 600), daemon=True).start()
        def app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")]); return [b"ok"]
    """))
    _bind, took, log = _boot_and_term("stuckapp:app", str(tmp_path), _env())
    assert took < 4.0, (took, log[-1500:])
    assert "강제 종료" in log                                  # 붙잡혔고, 강제 종료가 풀었다


def test_background_threads_are_not_started_at_import_under_gunicorn():
    """preload 마스터에 스레드가 붙지 않게 — gunicorn 설정이 세우는 `KGP_DEFER_BG_THREADS=1`이면 임포트 때 0개."""
    code = ("import threading, time, src.order_webhook as m; time.sleep(0.5); "
            "print(sorted(t.name for t in threading.enumerate() if t is not threading.main_thread()))")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=_env(KGP_DEFER_BG_THREADS="1"),
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    assert out.stdout.strip().splitlines()[-1] == "[]"


def test_stop_signal_wakes_loops_and_join_is_bounded(monkeypatch):
    from src.services import tick_watch as TW
    from src.utils import shutdown as SD
    monkeypatch.setenv("TICK_GAP_WATCH", "1")
    monkeypatch.setattr(TW, "_GAP_THREAD", {"t": None})
    monkeypatch.setattr(SD, "STOP", __import__("threading").Event())
    monkeypatch.setattr(SD, "_THREADS", [])
    assert TW.start_gap_watch(interval_sec=3600)
    t = TW._GAP_THREAD["t"]
    t0 = time.monotonic()
    assert SD.stop_all(join_sec=2.0) == 0                       # 한 시간 쉬던 루프가 바로 깨어 끝난다
    assert not t.is_alive() and time.monotonic() - t0 < 1.0


def test_health_is_light_and_does_not_boot_category_tables(monkeypatch):
    import src.order_webhook as W
    from src.uploaders import naver_categories as NC
    called = []
    monkeypatch.setattr(NC, "boot_refresh", lambda: called.append(1) or True)
    monkeypatch.setattr(W, "_NAVER_TREE_BOOT", {"pid": None})
    c = W.app.test_client()
    assert c.get("/health").status_code == 200 and called == []
    c.get("/health/deep")
    assert called == []                                         # 헬스체크는 첫 요청이어도 카테고리 표를 안 깨운다


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PG 레인 전용")
def test_schema_applied_once_then_skipped_and_serialized(caplog):
    import logging
    from src.db import pg
    caplog.set_level(logging.INFO, logger="src.db.pg")
    pg._schema_done = False
    pg.init_schema()
    pg._schema_done = False
    t0 = time.monotonic()
    pg.init_schema()
    assert any("지문 같음" in r.getMessage() for r in caplog.records)   # 두 번째 부팅 = 쿼리 한 번으로 끝
    assert time.monotonic() - t0 < 2.0
    with pg.query() as cur:
        cur.execute("SELECT value->>'digest' FROM app_state WHERE key=%s", (pg.SCHEMA_KEY,))
        assert (cur.fetchone() or [None])[0] == pg.schema_digest()
