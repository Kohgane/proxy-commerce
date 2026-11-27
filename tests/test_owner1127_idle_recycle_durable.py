"""오너 11-27 오후 감독 ⑥ — 「쉬는 동안 바닥」 재시작이 durable 작업이 도는 중에도 일꾼을 내리나 → 안 내린다(계약).

durable 작업은 `bg_job.start` 스레드 안에서 끝까지 돈다(`DJ.kick`) — 그 스레드는 샘플러 `watch("cron_djob:…")` 안이라
`post_request`의 「잡 진행 중이라 이번엔 남는다」가 쉬는 동안 바닥 길에도 그대로 걸린다. 잡이 끝난 뒤 첫 요청에서 갈아끼운다.
(11-26 18:10 재시작은 목록 만들기가 durable 이전 — 맨 스레드라 이 판정에 안 잡혔던 것.)
"""
from __future__ import annotations

import threading


def _gconf(monkeypatch, tmp_path):
    import importlib.util
    monkeypatch.setenv("WORKER_RSS_LIMIT_MB", "380")
    monkeypatch.setenv("WORKER_RSS_RESTART_STAMP", str(tmp_path / "stamp"))
    monkeypatch.setenv("INSTANCE_IDLE_RECYCLE_STAMP", str(tmp_path / "idle"))
    spec = importlib.util.spec_from_file_location("gconf_idle1127", "gunicorn.conf.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    monkeypatch.setattr(g, "_worker_rss_mb", lambda: 300)                        # 워커 상한 아래
    monkeypatch.setattr(g, "_instance_over", lambda: (False, 350, 420))           # 문지기 아래
    monkeypatch.setattr(g, "_idle_floor_due", lambda: (True, " · 쉬는 동안 합계 350 ≥ 330 (3틱 연속)"))
    return g


class _W:
    pid, alive = 9, True
    log = type("L", (), {"warning": lambda *a, **k: None})()


def test_idle_recycle_waits_for_running_durable_job(monkeypatch, tmp_path):
    g = _gconf(monkeypatch, tmp_path)
    from src.services import durable_job as DJ
    s = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: s.__setitem__(k, v))
    inside, release, seen = threading.Event(), threading.Event(), {}

    def step(key, rec, deadline):
        inside.set()
        release.wait(5)
        rec["state"] = "done"
        return rec
    DJ.register("t_idle1127", step)
    w = _W()
    DJ.begin("t:idle1127", "t_idle1127", {"progress": {"n": 0}})               # bg_job 스레드에서 끝까지
    assert inside.wait(5)
    g.post_request(w, None, None, None)
    seen["during"] = w.alive
    release.set()
    for _ in range(50):
        if DJ.get("t:idle1127").get("state") == "done":
            break
        threading.Event().wait(0.05)
    threading.Event().wait(0.1)
    assert seen["during"] is True                                                  # durable 작업 도는 중 — 남는다
    g.post_request(w, None, None, None)
    assert w.alive is False                                                        # 끝난 뒤 첫 요청에서 갈아끼움
