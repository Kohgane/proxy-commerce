"""순찰 106-A2(운영 10-26 22:09~22:13 KST) — 새 상품 하나가 수집 → 사진 번역 → 다듬기 8장 → 사전검증 2번을 한꺼번에 지난 뒤
인스턴스 합계가 223 → 334MB, 그 뒤 12시간 일 없이 350~355MB. 문지기(420)·워커 RSS 상한(380) 아래라 아무도 안 갈아끼웠다.

- 일 없는 틱(`tick-idle`)이 연달아 3번 합계 ≥ 260MB(순찰 135에서 300 → 260) → 다음 요청 끝에 워커를 갈아끼운다(잡 도는 중이면 안 함).
- 마스터 몫이면 갈아끼워도 안 내려간다 → 6시간에 한 번만(고리 방지).
- `rss:gate` 줄에 마스터 PSS(`m`)를 같이 적어, 다음에 오르면 어느 프로세스 몫인지 숫자로 가른다.
"""
import os
import runpy

import pytest


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    from src.db import image_translate_queue_pg as st
    from src.utils import rss
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    saved = dict(rss._IDLE_FLOOR)
    rss._IDLE_FLOOR.update(n=0, mb=-1)
    yield
    rss._IDLE_FLOOR.clear(); rss._IDLE_FLOOR.update(saved)


def test_idle_floor_counts_consecutive_high_ticks_and_resets():
    from src.utils import rss
    assert [rss.note_idle_floor(mb) for mb in (353, 350, 259, 261, 262, 355)] == [1, 2, 0, 1, 2, 3]
    assert rss.idle_recycle_due() == (True, 355, 3)
    rss.note_idle_floor(-1)                                              # 못 잰 틱은 이어짐을 끊는다
    assert rss.idle_recycle_due()[0] is False


def test_idle_floor_off_with_zero(monkeypatch):
    from src.utils import rss
    monkeypatch.setenv("INSTANCE_IDLE_RECYCLE_MB", "0")
    for _ in range(5):
        rss.note_idle_floor(500)
    assert rss.idle_recycle_due()[0] is False


class _Log:
    def __init__(self):
        self.lines = []

    def warning(self, msg, *a, **k):
        self.lines.append(msg % a)


def _worker():
    class _W:
        alive, pid = True, 4106
    w = _W()
    w.log = _Log()
    return w


def _conf(monkeypatch, tmp_path, *, rss_mb=280, jobs=()):
    monkeypatch.setenv("KGP_DEFER_BG_THREADS", os.environ.get("KGP_DEFER_BG_THREADS", "1"))   # 설정 파일의 setdefault를 되돌린다
    g = runpy.run_path("gunicorn.conf.py")
    pr = g["post_request"]
    gl = pr.__globals__
    monkeypatch.setitem(gl, "_RSS_LIMIT_MB", 380)
    monkeypatch.setitem(gl, "_RSS_STAMP", str(tmp_path / "rss_stamp"))
    monkeypatch.setitem(gl, "_IDLE_STAMP", str(tmp_path / "idle_stamp"))
    monkeypatch.setitem(gl, "_worker_rss_mb", lambda: rss_mb)
    monkeypatch.setitem(gl, "_active_jobs", lambda: list(jobs))
    monkeypatch.setitem(gl, "_instance_over", lambda: (False, 353, 420))
    return pr, gl


def test_post_request_recycles_after_idle_high_floor_once_per_gap(monkeypatch, tmp_path):
    from src.utils import restart_log as R
    from src.utils import rss
    pr, gl = _conf(monkeypatch, tmp_path)
    w = _worker()
    pr(w, None, None, None)
    assert w.alive is True                                                # 틱 0번 — 그대로
    for mb in (353, 352, 355):
        rss.note_idle_floor(mb)
    pr(w, None, None, None)
    assert w.alive is False and "쉬는 동안 합계 355 ≥ 260 (3틱 연속)" in w.log.lines[-1]
    row = R.rows()[-1]
    assert row["kind"] == "exit" and row["reason"] == "쉬는 동안 바닥" and row["worker_mb"] == 280
    w2 = _worker()                                                        # 새 워커도 바닥이 그대로(마스터 몫)여도 6시간 안엔 안 갈아끼운다
    monkeypatch.setitem(gl, "_RSS_STAMP", str(tmp_path / "rss_stamp2"))
    pr(w2, None, None, None)
    assert w2.alive is True


def test_post_request_waits_while_a_job_runs(monkeypatch, tmp_path):
    from src.utils import rss
    pr, _gl = _conf(monkeypatch, tmp_path, jobs=["pv_job"])
    for mb in (353, 352, 355):
        rss.note_idle_floor(mb)
    w = _worker()
    pr(w, None, None, None)
    assert w.alive is True and "진행 중이라 이번엔 남는다" in w.log.lines[-1]


def test_gate_row_carries_master_pss_and_tick_feeds_the_counter():
    from src.utils import rss
    parts = rss.instance_parts()
    assert set(parts) == {"pss", "cg", "w", "m"} and parts["m"] == -1     # gunicorn 밖이면 -1
    from tests._ast_probe import callers_of
    import src.pricing.cron as cron
    assert callers_of(cron, "note_idle_floor")                            # 틱이 일 없는 합계를 센다(호출 구조로)
