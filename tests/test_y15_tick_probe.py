"""Y15 순찰 41(오너 2026-10-23) — 메모리 바닥: MEM_TRACE 대신 틱 경계 프로브.

리스 틱 4종(translate-pilot·imgko-auto·reject-watch·optko-auto) 시작/끝 RSS·스레드 수 + 요청 100개마다 한 줄 → `rss:ticks`(400줄).
"""
import pytest


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("TICK_PROBE", "1")
    from src.db import image_translate_queue_pg as st
    from src.services import workers as W
    data = {}
    monkeypatch.setattr(st, "_enabled", lambda: False)          # 순찰 57: 원자 쓰기(state_update)도 같은 저장소
    monkeypatch.setattr(st, "_MEM_STATE", data)
    monkeypatch.setattr(W, "_pg_on", lambda: False)
    W._PROBE_OPEN.clear()
    W._MEM.clear()
    yield data
    W._PROBE_OPEN.clear()


def test_lease_start_once_and_end_on_release(store):
    from src.services import workers as W
    assert W.lease("imgko-auto") and W.lease("imgko-auto") and W.lease("imgko-auto")   # 장마다 갱신 — 시작은 한 줄
    W.release("imgko-auto")
    assert W.lease("naver-order-poll")                           # 대상 아닌 리스는 안 남긴다
    W.release("naver-order-poll")
    rows = store["rss:ticks"]["rows"]
    assert [(r["name"], r["phase"]) for r in rows] == [("imgko-auto", "start"), ("imgko-auto", "end")]
    r = rows[0]
    assert r["kind"] == "tick" and isinstance(r["mb"], int) and r["threads"] >= 1 and "svc" in r and r["at"]


def test_every_100th_request_is_sampled_and_rows_are_capped(store, monkeypatch):
    import src.order_webhook as OW
    from src.utils import render_worker as RW
    import threading
    import time
    monkeypatch.setattr(OW, "_REQ_PROBE_EVERY", 3)
    monkeypatch.setattr(OW, "_REQ_PROBE_FLUSH_N", 1)              # 순찰 57: 매 요청 DB 카운터에 더한다(테스트만)
    monkeypatch.setattr(OW, "_REQ_PROBE", {"pending": 0, "flushed_at": time.monotonic(), "lock": threading.Lock()})
    c = OW.app.test_client()
    for _ in range(7):
        c.get("/health/live")
    rows = [r for r in store["rss:ticks"]["rows"] if r["kind"] == "req"]
    assert [r["n"] for r in rows] == [3, 6] and all("mb" in r and "endpoint" in r for r in rows)
    for i in range(RW.TICKS_KEEP + 5):
        RW.record_tick("req", n=i)
    assert len(store["rss:ticks"]["rows"]) == RW.TICKS_KEEP     # 400줄 상한


def test_probe_off_switch(store, monkeypatch):
    from src.services import workers as W
    monkeypatch.setenv("TICK_PROBE", "0")
    W.lease("optko-auto")
    W.release("optko-auto")
    assert "rss:ticks" not in store
