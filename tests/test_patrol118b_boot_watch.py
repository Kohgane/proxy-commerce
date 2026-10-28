"""순찰 118b — 배포 뒤 「떴지만 안 받는」 날 스스로 알아채고 다시 뜬다(`src/utils/boot_watch.py` · `gunicorn.conf.py` 훅).

실제 gunicorn으로 돌린 하네스(PR 본문): 포크 전 멈춤 11초 · 워커 미준비 16초 · 자기 /health 안 닿음 61초 → 셋 다 `exit 3`(Render가 다시 띄움),
정상 부팅 40초 동안 오탐 0 · 실제 설정 40회 부팅 재현 40/40 정상.
"""
import json
import os
import runpy
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    monkeypatch.setenv("KGP_BOOT_STAGE_FILE", str(tmp_path / "stages.json"))
    for k in ("KGP_BOOT_FORK_STUCK_SEC", "KGP_BOOT_READY_SEC", "KGP_BOOT_WATCH_EXIT", "KGP_BOOT_WATCH"):
        monkeypatch.delenv(k, raising=False)
    yield


def test_marks_three_stages_and_summary():
    from src.utils import boot_watch as B
    B.mark("master_ready")
    B.mark("fork_start", age=1)
    B.mark("fork_done", age=1)
    st = B.read()
    assert set(st) >= {"master_ready", "fork_start", "fork_done", "unready_since"}
    B.mark("worker_ready", age=1)
    st = B.read()
    assert "unready_since" not in st and st["worker_ready"]["pid"] == os.getpid()
    s = B.summary(st)
    assert set(s) >= {"master_ready", "fork_start", "fork_done", "worker_ready", "master_age_sec"} and s["master_ready"] == 0.0
    B.mark("nope")                                                              # 모르는 단계는 안 적는다
    assert "nope" not in B.read()


def test_verdict_pre_fork_worker_init_and_healthy():
    from src.utils import boot_watch as B
    t0 = 1000.0
    assert B.verdict({}, t0) is None
    st = {"fork_start": {"t": t0}}
    assert B.verdict(st, t0 + 59) is None
    assert B.verdict(st, t0 + 60) == {"stage": "pre_fork", "since_sec": 60.0}
    st = {"fork_start": {"t": t0}, "fork_done": {"t": t0 + 1}, "unready_since": t0 + 1}
    assert B.verdict(st, t0 + 180) is None
    assert B.verdict(st, t0 + 181)["stage"] == "worker_init"
    # gunicorn이 한 번 갈아끼워(새 포크) 다시 기다려도 묶음의 처음부터 잰다
    st2 = dict(st, fork_start={"t": t0 + 125}, fork_done={"t": t0 + 126})
    assert B.verdict(st2, t0 + 181)["stage"] == "worker_init"
    ok = dict(st, worker_ready={"t": t0 + 5})
    ok.pop("unready_since")
    assert B.verdict(ok, t0 + 10_000) is None                                    # 준비된 뒤엔 판정 없음


def test_bail_records_kills_workers_and_exits(monkeypatch):
    from src.utils import boot_watch as B
    from src.utils import restart_log as RL
    killed, exited = [], []
    monkeypatch.setattr(os, "kill", lambda p, s: killed.append((p, s)))
    srv = type("S", (), {"WORKERS": {41: object(), 42: object()}})()
    row = B.bail(srv, {"stage": "pre_fork", "since_sec": 61.0}, exit_fn=exited.append)
    assert exited == [3] and [p for p, _ in killed] == [41, 42] and row["workers"] == [41, 42]
    got = [r for r in RL.rows() if r.get("kind") == "boot_stuck"]
    assert got and got[-1]["stage"] == "pre_fork" and got[-1]["exit"] is True


def test_bail_record_only_when_exit_off(monkeypatch):
    from src.utils import boot_watch as B
    monkeypatch.setenv("KGP_BOOT_WATCH_EXIT", "0")
    monkeypatch.setattr(os, "kill", lambda p, s: pytest.fail("죽이면 안 된다"))
    exited = []
    row = B.bail(type("S", (), {"WORKERS": {7: 1}})(), {"stage": "worker_init", "since_sec": 200}, exit_fn=exited.append)
    assert exited == [] and row["exit"] is False


def _run_loop(B, monkeypatch, probe_results, *, ready_age=1.0):
    import time
    B.mark("master_ready")
    B.mark("fork_start")
    B.mark("fork_done")
    B.mark("worker_ready")
    st = B.read()
    st["worker_ready"]["t"] = time.time() - ready_age
    with open(B.stage_file(), "w", encoding="utf-8") as fh:
        json.dump(st, fh)
    monkeypatch.setenv("KGP_BOOT_PROBE_EVERY_SEC", "1")
    seq = list(probe_results)
    calls = []

    def _probe(port, timeout=15.0):
        calls.append(port)
        return seq.pop(0) if seq else True
    monkeypatch.setattr(B, "_probe", _probe)
    bails = []
    monkeypatch.setattr(B, "bail", lambda server, why, **kw: bails.append(why))
    stop = threading.Event()
    n = {"i": 0}
    clock = {"t": time.time()}

    def _sleep(_s):
        n["i"] += 1
        clock["t"] += 2
        if n["i"] > 12:
            stop.set()
    monkeypatch.setattr(B.time, "time", lambda: clock["t"])
    B._loop(object(), "8000", sleep=_sleep, stop=stop)
    return calls, bails


def test_loop_bails_after_three_unanswered_self_probes(monkeypatch):
    from src.utils import boot_watch as B
    calls, bails = _run_loop(B, monkeypatch, [False, False, False])
    assert len(calls) == 3 and bails and bails[0]["stage"] == "no_response" and bails[0]["probe_fails"] == 3


def test_loop_stops_probing_after_first_answer(monkeypatch):
    from src.utils import boot_watch as B
    calls, bails = _run_loop(B, monkeypatch, [False, True])
    assert len(calls) == 2 and bails == []                                       # 한 번 붙으면 그 세대는 더 안 친다


def test_loop_does_not_probe_outside_the_boot_window(monkeypatch):
    from src.utils import boot_watch as B
    calls, bails = _run_loop(B, monkeypatch, [False] * 5, ready_age=10_000)
    assert calls == [] and bails == []                                           # 바쁜 운영 중에는 치지 않는다


def test_watch_off_marks_but_no_thread(monkeypatch):
    from src.utils import boot_watch as B
    monkeypatch.setenv("KGP_BOOT_WATCH", "0")
    assert B.start(object()) is None and "master_ready" in B.read()


def test_gunicorn_hooks_mark_every_stage_and_boot_row_carries_them(monkeypatch):
    from src.utils import boot_watch as B
    from src.utils import restart_log as RL
    g = runpy.run_path(os.path.join(ROOT, "gunicorn.conf.py"))
    started = []
    monkeypatch.setattr(B, "start", lambda server: (started.append(server), B.mark("master_ready")))
    srv = type("Srv", (), {"log": type("L", (), {"warning": staticmethod(lambda *a, **k: None)})()})()
    g["when_ready"](srv)
    assert started == [srv]
    monkeypatch.setenv("KGP_PREFORK_TRIM", "0")
    monkeypatch.setenv("KGP_GC_FREEZE", "0")
    g["pre_fork"](srv, type("W", (), {"age": 1})())
    assert set(B.read()) >= {"master_ready", "fork_start", "fork_done"}
    import src.order_webhook as app_mod
    monkeypatch.setattr(app_mod, "start_background_threads", lambda: None)
    monkeypatch.setattr(RL, "arm_no_traffic", lambda *a, **k: None)
    w = type("W", (), {"age": 1, "cfg": None, "log": srv.log})()
    g["post_worker_init"](w)
    assert "worker_ready" in B.read()
    boot = [r for r in RL.rows() if r.get("kind") == "boot"][-1]
    assert set(boot["stages"]) >= {"master_ready", "fork_start", "fork_done", "worker_ready"}


def test_pre_fork_marks_done_even_if_body_fails(monkeypatch):
    from src.utils import boot_watch as B
    g = runpy.run_path(os.path.join(ROOT, "gunicorn.conf.py"))

    def _boom(server, worker):
        raise RuntimeError("x")
    g["pre_fork"].__globals__["_pre_fork_body"] = _boom
    with pytest.raises(RuntimeError):
        g["pre_fork"](object(), type("W", (), {"age": 2})())
    st = B.read()
    assert st["fork_done"]["t"] >= st["fork_start"]["t"]                        # 끝 표시는 남는다(포크 전 멈춤 오판 없음)
