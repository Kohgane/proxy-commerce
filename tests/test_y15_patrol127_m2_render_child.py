"""순찰 127 M2(운영 10-26 22:09 KST) — 다듬기 8장 그린 뒤 웹 워커 RSS 182 → 245MB, 일 없이 12시간 그대로(gc·malloc_trim으로도 안 돌아옴).

로컬 실측(실사진 4장 · 앱 전체 임포트): 웹 프로세스 안에서 그리면 첫 장 뒤 RSS +52MB(익명 +20) 상주 · 자식에서 그리면 부모 +18(익명 +12),
자식(그리는 동안 130MB)은 줄이 비면 내려가 통째로 돌아간다. 첫 장 1.9초 · 다음 장 1.4초(자식 띄우는 값 ~0.5초).

- 운영(gunicorn)에선 그리기를 자식 프로세스 하나에서(`RENDER_PROCESS` auto) · 테스트·개발은 예전처럼 스레드.
- 줄이 `RENDER_PROC_IDLE_SEC` 비면 자식을 내린다.
- 한 장이 상한을 넘으면 자식을 죽인다(스레드와 달리 멈춘 그리기가 다음 장을 막지 않는다 — M1과 같은 줄).
"""
import glob
import os
import time

import pytest


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        with open(f"/proc/{pid}/status") as fh:
            return "State:\tZ" not in fh.read()
    except OSError:
        return False


@pytest.fixture
def child_mode(monkeypatch):
    from src.utils import render_worker as RW
    monkeypatch.setenv("RENDER_PROCESS", "1")
    monkeypatch.setenv("RENDER_WORKER", "1")
    monkeypatch.setenv("RENDER_PROC_IDLE_SEC", "1")
    yield RW
    pool = RW._STATE.pop("pool", None)
    if pool is not None:
        RW._kill_pool(pool)
    t = RW._STATE.get("thread")
    if t is not None:
        t.join(timeout=5)


def test_auto_is_off_outside_gunicorn(monkeypatch):
    from src.utils import render_worker as RW
    monkeypatch.delenv("RENDER_PROCESS", raising=False)
    assert RW.proc_enabled() is False
    from src.utils import rss
    monkeypatch.setattr(rss, "under_gunicorn", lambda: True)
    assert RW.proc_enabled() is True
    monkeypatch.setenv("RENDER_PROCESS", "0")
    assert RW.proc_enabled() is False


def test_render_runs_in_a_child_that_goes_away_when_idle(child_mode):
    RW = child_mode
    pid = RW.run(os.getpid, _name="probe", _timeout=60)
    assert pid != os.getpid() and _alive(pid) and RW.child_pid() == pid       # 그리기는 자식에서
    assert RW.run(os.getpid, _name="probe2", _timeout=60) == pid              # 줄이 이어지면 같은 자식
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and (RW.child_pid() or _alive(pid)):
        time.sleep(0.2)
    assert RW.child_pid() == 0 and not _alive(pid)                             # 줄이 비면 자식을 내린다


def test_a_stuck_render_kills_the_child_and_the_next_one_still_runs(child_mode):
    RW = child_mode
    first = RW.run(os.getpid, _name="probe", _timeout=60)
    with pytest.raises(Exception) as ei:
        RW.run(time.sleep, 30, _name="stuck", _timeout=1)
    assert "Timeout" in type(ei.value).__name__
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _alive(first):
        time.sleep(0.1)
    assert not _alive(first)                                                   # 멈춘 자식은 죽였다
    again = RW.run(os.getpid, _name="probe3", _timeout=60)
    assert again != first and _alive(again)                                    # 다음 장은 새 자식에서


def test_real_render_through_the_child(child_mode):
    from src.services import image_edit as IE
    raw = open(sorted(glob.glob("tests/fixtures/realimages/**/*.jpg", recursive=True))[0], "rb").read()
    b = {"id": "b0", "x": 20, "y": 40, "w": 400, "h": 60, "src": "原文", "tgt": "번역"}
    out = child_mode.run(IE.render_local, raw, 1.0, [], [(b, "스마트워치 호환")], others=[b], _name="real", _timeout=60)
    assert out["ok"] and out["bytes"][:3] == b"\xff\xd8\xff"                   # JPEG 그대로 돌아온다
