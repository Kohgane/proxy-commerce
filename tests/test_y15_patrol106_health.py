"""순찰 106-F(오너 2026-10-26) — 10-25 19:35~22:14 159분 무응답: 배포 부팅 기록 뒤 요청·틱 0, 헬스체크는 몰랐다.

- `/health`: pid · 부팅 뒤 요청 수 · 마지막 틱 시각 · 틱 공백(분). 공백 ≥ `HEALTH_TICK_STALE_MIN`(20)이면 503(Render가 갈아끼움).
  부팅 뒤 아직 틱이 없으면 부팅 시각부터 잰다. 503은 gunicorn 워커로 뜬 프로세스만(개발·테스트는 나이만).
- 부팅 60초 안 끝난 요청 0 → `rss:restart`에 `no_traffic` 한 줄(헬스체크도 요청이라, 0이면 밖에서 아예 안 닿은 것).
"""
import pytest


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    from src.db import image_translate_queue_pg as q
    from src.utils import restart_log as rl
    q.reset_for_tests()
    saved = (dict(rl._LAST_REQ), dict(rl._BOOT_AT), dict(rl._LAST_TICK))
    yield
    rl._LAST_REQ.clear(); rl._LAST_REQ.update(saved[0])
    rl._BOOT_AT.clear(); rl._BOOT_AT.update(saved[1])
    rl._LAST_TICK.clear(); rl._LAST_TICK.update(saved[2])
    q.reset_for_tests()


def _booted(monkeypatch, *, ago_min=0.0, tick_ago_min=None):
    import time
    from src.utils import restart_log as rl
    from src.utils import rss
    monkeypatch.setattr(rss, "under_gunicorn", lambda: True)
    now = time.monotonic()
    rl._BOOT_AT.update(at=now - ago_min * 60, noted=True)
    rl._LAST_TICK["at"] = 0.0 if tick_ago_min is None else now - tick_ago_min * 60
    rl._LAST_REQ["n"] = 0
    return now


def test_snapshot_measures_gap_from_boot_until_the_first_tick(monkeypatch):
    from src.utils import restart_log as rl
    now = _booted(monkeypatch, ago_min=5)
    s = rl.health_snapshot(now)
    assert s["ticked_since_boot"] is False and s["last_tick_at"] is None and 4.9 <= s["tick_gap_min"] <= 5.1
    assert s["stale"] is False and s["stale_after_min"] == 20
    now = _booted(monkeypatch, ago_min=25)
    assert rl.health_snapshot(now)["stale"] is True                       # 부팅 25분 · 틱 0 = 159분 무응답의 모양
    now = _booted(monkeypatch, ago_min=60, tick_ago_min=3)
    s = rl.health_snapshot(now)
    assert s["stale"] is False and s["ticked_since_boot"] and s["last_tick_at"]


def test_health_returns_503_when_ticks_stopped_and_200_after_a_tick(monkeypatch):
    from src.order_webhook import app
    from src.utils import restart_log as rl
    c = app.test_client()
    _booted(monkeypatch, ago_min=21)
    r = c.get("/health")
    j = r.get_json()
    assert r.status_code == 503 and j["status"] == "stale" and j["process"]["tick_gap_min"] >= 20
    assert j["process"]["pid"] > 0 and isinstance(j["process"]["requests"], int)
    rl.note_tick()
    r = c.get("/health")
    assert r.status_code == 200 and r.get_json()["status"] == "ok" and r.get_json()["process"]["requests"] >= 1
    monkeypatch.setenv("HEALTH_TICK_STALE_MIN", "0")                       # 끄면 나이만(200)
    _booted(monkeypatch, ago_min=300)
    assert c.get("/health").status_code == 200


def test_health_never_503s_outside_gunicorn(monkeypatch):
    import time
    from src.order_webhook import app
    from src.utils import restart_log as rl
    rl._BOOT_AT.update(at=time.monotonic() - 3600, noted=False)          # 개발 서버·테스트(note_boot 안 거침)
    rl._LAST_TICK["at"] = 0.0
    assert app.test_client().get("/health").status_code == 200


def test_no_traffic_row_only_when_nothing_arrived(monkeypatch):
    from src.utils import restart_log as rl
    now = _booted(monkeypatch, ago_min=1)
    row = rl.check_no_traffic(now)
    assert row and row["requests"] == 0 and row["since_boot_sec"] >= 59
    got = [r for r in rl.rows() if r.get("kind") == "no_traffic"]
    assert len(got) == 1 and got[0]["pid"] == row["pid"]
    rl.touch_request()
    assert rl.check_no_traffic(now) is None                                # 하나라도 끝났으면 안 적는다


def test_boot_resets_counters_and_arms_the_timer(monkeypatch):
    import threading
    from src.utils import restart_log as rl
    rl.touch_request(); rl.note_tick()
    rl.note_boot(4242, 120)
    assert rl._LAST_REQ["n"] == 0 and rl._LAST_TICK["at"] == 0.0 and rl._BOOT_AT["noted"] is True
    started = []
    monkeypatch.setattr(threading.Timer, "start", lambda self: started.append((self.interval, self.daemon)))
    rl.arm_no_traffic()
    assert started == [(60, True)]
    import os
    import runpy
    from tests._ast_probe import callers_of, calls_in
    import src.pricing.cron as cron
    monkeypatch.setenv("KGP_DEFER_BG_THREADS", os.environ.get("KGP_DEFER_BG_THREADS", "1"))   # 설정 파일의 setdefault를 되돌린다
    conf = runpy.run_path("gunicorn.conf.py")
    assert "arm_no_traffic" in calls_in(conf["post_worker_init"])           # 부팅 훅이 타이머를 건다(호출 구조로)
    assert callers_of(cron, "_note_tick")                                    # 틱이 끝날 때 나이를 적는다
