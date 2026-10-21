"""Y14-2(오너 2026-10-20 「413MB 상시 점유」) — 지연 임포트 · 일 끝난 자리에서 malloc_trim.

로컬 실측(같은 스크립트, main 44e7f802 → 이 브랜치): 앱 import 111 → 99MB(gspread 부팅 체인 제거) ·
8스레드 큰 사진 작업 뒤 워커 회차 끝 722MB → 200MB(`record_run` → `rss.release`).
"""
import subprocess
import sys


def test_sheets_does_not_load_gspread_at_import():
    code = ("import sys; import src.utils.sheets as S; print('gspread' in sys.modules, 'oauth2client' in sys.modules);"
            "S.gspread.exceptions; print('gspread' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    assert out == ["False", "False", "True"]                       # 처음 쓸 때 실린다


def test_app_boot_does_not_load_heavy_modules():
    code = ("import os, sys; os.environ['SELLER_CONSOLE_AUTH']='0'; from src.order_webhook import app;"
            "print([m for m in ('gspread','anthropic','cv2','numpy','pypinyin') if m in sys.modules])")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    assert out == "[]"


def test_worker_round_end_releases_heap(monkeypatch):
    from src.services import workers as W
    from src.utils import rss
    calls = []
    monkeypatch.setattr(rss, "release", lambda reason="": calls.append(reason) or (0, 0))
    monkeypatch.setattr(W, "_state", lambda: type("S", (), {"state_get": staticmethod(lambda k: {}),
                                                             "state_set": staticmethod(lambda k, v: None)}))
    W.record_run("imgko-auto", 3)
    W.record_run("reject-watch", 0)                                # 한 일이 없으면 부르지 않는다
    assert calls == ["worker:imgko-auto"]


def test_release_trims_and_reports(monkeypatch):
    monkeypatch.setenv("RSS_RELEASE", "1")                       # conftest가 테스트 프로세스에선 끈다 — 이 계약은 켜고 잰다
    from src.utils import rss, render_worker
    seq = iter([500, 180])
    monkeypatch.setattr(rss, "read_mb", lambda: (next(seq), 0))
    trimmed = []
    monkeypatch.setattr(render_worker, "trim", lambda: trimmed.append(1) or True)
    assert rss.release("t") == (500, 180) and trimmed == [1]


def test_heavy_request_releases_after(monkeypatch):
    from src.utils import rss
    calls = []
    monkeypatch.setattr(rss, "release", lambda reason="": calls.append(reason) or (0, 0))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="u-mem", user_email="u-mem@example.com", user_role="seller")
    c.post("/seller/collect/upload", json={"product": {}, "markets": []})
    c.get("/seller/")
    assert calls == ["collect_upload"]                             # 등록 요청 뒤에만(대시보드는 아님)


def test_every_tick_logs_idle_instance_mb(monkeypatch):
    """Y14-e — 문지기 기록(`rss:gate`)은 백그라운드 일을 시작할 때만 남았다 → 틱마다 드레인 전에 한 줄(job=tick-idle)."""
    import src.seller_console.translate_worker as TW
    import src.pricing.cron as CRON
    from src.utils import bg_job, rss
    rows = []
    monkeypatch.setattr(bg_job, "_gate_log", lambda name, ok, cur, lim: rows.append((name, ok, cur, lim)))
    monkeypatch.setattr(rss, "start_ok", lambda: (True, 233, 420))
    order = []
    monkeypatch.setattr(TW, "drain_once", lambda limit=10, time_budget_sec=None:
                        order.append("drain") or {"ok": True, "processed": 0, "remaining": 0})
    monkeypatch.setattr(CRON, "_run_pilot_finish_tick", lambda chunk=3, time_budget_sec=None: {})
    from src.services import workers as W
    monkeypatch.setattr(W, "lease", lambda *a, **k: True)
    from src.order_webhook import app
    CRON._tick_lock.acquire(blocking=False)
    CRON._run_full_tick(app, limit=1, pilot_chunk=1, tick_budget=30.0)
    assert rows and rows[0] == ("tick-idle", True, 233, 420) and order == ["drain"]


def test_release_switch_off_does_nothing(monkeypatch):
    from src.utils import rss
    import src.utils.render_worker as RW
    called = []
    monkeypatch.setattr(RW, "trim", lambda: called.append(1))
    monkeypatch.setenv("RSS_RELEASE", "0")
    assert rss.release("t") == (0, 0) and called == []


def test_prevalidate_job_releases_even_when_body_raises(monkeypatch):
    """Y14(운영 10-21 08:00~08:10): 잡 넷이 차례로 돌았는데 잡마다 프로세스 바닥이 170→204→266→313MB로 올랐다.
    반환은 몸통 끝에만 있어 몸통·끝 기록이 예외로 끝나면 건너뛰었다 — 이제 바깥에서 늘 한 번."""
    from src.seller_console import views as V
    from src.utils import rss
    calls = []
    monkeypatch.setattr(rss, "release", lambda reason="": calls.append(reason) or (300, 200))
    monkeypatch.setattr(V, "_pv_wait_memory", lambda job_id, markets: (True, 200, 420))

    def boom(*a, **k):
        raise RuntimeError("몸통 실패")
    monkeypatch.setattr(V, "_pv_job_body", boom)
    try:
        V._pv_job("jtest0001", {}, ["coupang:gogane"], None)
    except RuntimeError:
        pass
    assert calls == ["prevalidate:fail"]
    assert V._pv_semaphore().acquire(blocking=False)               # 자리도 돌려줬다
    V._pv_semaphore().release()

    calls.clear()
    monkeypatch.setattr(V, "_pv_job_body", lambda *a, **k: None)
    V._pv_job("jtest0002", {}, ["coupang:gogane"], None)
    assert calls == ["prevalidate"]                                # 정상 끝 — 한 번만


def test_late_market_thread_releases_when_it_finishes(monkeypatch):
    """Y14(운영 10-21 08:01 우주대행 12초 초과): 시간이 넘은 마켓 스레드는 잡 뒤에도 돈다 — 끝나는 순간 반환."""
    import threading
    import time
    from src.seller_console import views as V
    from src.utils import rss
    calls, gate = [], threading.Event()
    monkeypatch.setattr(rss, "release", lambda reason="": calls.append(reason) or (0, 0))
    monkeypatch.setattr(V, "_PV_MARKET_TIMEOUT_SEC", 0.2)
    monkeypatch.setattr(V, "_pv_update", lambda job_id, **kw: {})

    class _R:
        market, error_code = "", ""

    class _D:
        def prevalidate(self, pd, markets):
            if markets == ["coupang:woojoo"]:
                gate.wait(5)
            return [_R()]
    monkeypatch.setattr(V, "_pv_dict", lambda r, rc: {"ok": True})
    out = V._pv_run_markets("jtest0003", {}, ["coupang:gogane", "coupang:woojoo"], _D(), None, time.time() + 10)
    assert len(out) == 1 and calls == []                           # 늦은 마켓은 아직 도는 중
    gate.set()
    for _ in range(50):
        if calls:
            break
        time.sleep(0.05)
    assert calls == ["pv_orphan"]
