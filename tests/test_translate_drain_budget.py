"""tests/test_translate_drain_budget.py — /cron/translate-drain 시간예산 드레인.

[[동기 대량 라우트 타임아웃 지뢰]] 재발 방지: 25초 도달 시 즉시 중단·부분 결과(HTTP 200)·다음 크론 이어서.
PG·번역 체인·시계를 전부 주입해 오프라인·결정적으로 검증(네트워크·실시간 sleep 0).
"""
from __future__ import annotations

import json
import pytest


def _wire(monkeypatch, *, total_jobs, item_secs=10.0):
    """가짜 큐(무한 pending) + 가짜 번역기 + 주입 시계. 번역 1건당 item_secs 경과를 시뮬레이션."""
    from src.db import translation_jobs_pg as jobs
    from src.seller_console import translate_worker as TW
    from src.seller_console import collect_history_store as CHS
    from src.seller_console import translation_usage as TU

    clock = {"t": 0.0}
    state = {"leased": 0, "completed": 0}

    monkeypatch.setattr(jobs, "enabled", lambda: True)

    def _lease(n, *, worker_id, **kw):
        if state["leased"] >= total_jobs:
            return []
        state["leased"] += 1
        jid = state["leased"]
        return [{"job_id": f"j{jid}", "user_id": "u1", "item_id": f"i{jid}",
                 "attempts": 0, "max_attempts": 3}]
    monkeypatch.setattr(jobs, "lease", _lease)
    monkeypatch.setattr(jobs, "counts",
                        lambda: {"pending": max(0, total_jobs - state["leased"])})
    monkeypatch.setattr(jobs, "complete", lambda jid, **kw: state.__setitem__("completed", state["completed"] + 1) or True)
    monkeypatch.setattr(jobs, "fail", lambda jid, **kw: "failed")

    monkeypatch.setattr(CHS, "get",
                        lambda item_id, seller_ids=None: {"title": "Wireless Earbuds",
                                                          "extra_json": json.dumps({"title_en": "Wireless Earbuds",
                                                                                    "description": "Great sound"})})
    monkeypatch.setattr(CHS, "update", lambda item_id, seller_ids=None, **f: True)
    monkeypatch.setattr(TU, "free_limit", lambda: 999999)
    monkeypatch.setattr(TU, "get_used", lambda uid: 0)
    monkeypatch.setattr(TU, "increment", lambda uid, n: None)

    class _FakeTranslator:
        def translate_product(self, payload):
            clock["t"] += item_secs          # 번역 1건 = item_secs 경과(체인 지연 시뮬레이션)
            return {"provider": "papago", "title_ko": "무선 이어버드",
                    "description_ko": "훌륭한 음질", "attempts": 1, "detected_lang": "en"}
    import src.seller_console.ai.translator as TR
    monkeypatch.setattr(TR, "AITranslator", _FakeTranslator)

    return TW, (lambda: clock["t"]), state


def test_budget_stops_at_threshold_and_returns_partial(monkeypatch):
    # 큐 무한(100건) + 항목당 10초 + 예산 25초 → 3건 처리 후 즉시 중단(부분 결과).
    TW, clk, state = _wire(monkeypatch, total_jobs=100, item_secs=10.0)
    out = TW.drain_once(limit=50, time_budget_sec=25.0, monotonic_fn=clk)
    assert out["ok"] is True and out["processed"] == 3            # 0·10·20 통과, 30에서 중단
    assert out["budget_exhausted"] is True                        # 예산 소진 플래그
    assert out["success"] == 3 and out["remaining"] > 0           # 남은 건 = 다음 크론
    assert out["elapsed_sec"] >= 25                               # 예산 도달


def test_drains_fully_when_queue_empties_before_budget(monkeypatch):
    # 큐 4건 + 항목당 1초 + 예산 25초 → 큐 소진(4건)·예산 미소진.
    TW, clk, state = _wire(monkeypatch, total_jobs=4, item_secs=1.0)
    out = TW.drain_once(limit=50, time_budget_sec=25.0, monotonic_fn=clk)
    assert out["processed"] == 4 and out["budget_exhausted"] is False
    assert out["remaining"] == 0                                  # 전건 처리


def test_limit_caps_even_within_budget(monkeypatch):
    # 예산 넉넉해도 limit이 상한(무한 큐·항목당 0초·limit 5).
    TW, clk, state = _wire(monkeypatch, total_jobs=100, item_secs=0.0)
    out = TW.drain_once(limit=5, time_budget_sec=25.0, monotonic_fn=clk)
    assert out["processed"] == 5 and out["budget_exhausted"] is False and out["remaining"] > 0


def test_env_budget_override(monkeypatch):
    monkeypatch.setenv("TRANSLATE_DRAIN_BUDGET_SEC", "12")
    TW, clk, state = _wire(monkeypatch, total_jobs=100, item_secs=10.0)
    out = TW.drain_once(limit=50, monotonic_fn=clk)              # 예산 인자 없음 → env 12s
    assert out["processed"] == 2 and out["budget_exhausted"] is True   # 0·10 통과, 20에서 중단


def test_noop_without_pg_has_budget_fields(monkeypatch):
    for v in ("DATABASE_URL", "SUPABASE_DB_URL"):
        monkeypatch.delenv(v, raising=False)
    from src.db import pg
    pg.reset_state()
    from src.seller_console.translate_worker import drain_once
    out = drain_once(limit=5)
    assert out["processed"] == 0 and out["budget_exhausted"] is False and out["remaining"] == 0


def test_route_returns_202_immediately_and_spawns_tick(monkeypatch):
    # cron-job.org 30s 하드 상한 → 라우트는 즉시 202(작업 시작됨)만 반환, 실작업은 백그라운드.
    monkeypatch.delenv("CRON_SECRET", raising=False)
    import src.pricing.cron as CRON
    spawned = {}
    monkeypatch.setattr(CRON, "_spawn_background_tick",
                        lambda app, limit, pilot_chunk, tick_budget: spawned.update(
                            {"limit": limit, "pilot_chunk": pilot_chunk, "budget": tick_budget}))
    # 락이 자유 상태여야(다른 테스트 잔류 방지) — 강제 초기화.
    if CRON._tick_lock.locked():
        try: CRON._tick_lock.release()
        except RuntimeError: pass
    from src.order_webhook import app
    c = app.test_client()
    r = c.post("/cron/translate-drain?limit=7&pilot_chunk=2")
    assert r.status_code == 202                                   # 즉답 202 = cron 성공 판정
    d = r.get_json()
    assert d["status"] == "accepted" and d["limit"] == 7 and d["pilot_chunk"] == 2
    assert spawned == {"limit": 7, "pilot_chunk": 2, "budget": CRON._tick_budget_sec()}
    # 스폰(몽키패치)이 락을 안 풀었으므로 라우트가 잡은 락은 여전히 held → 정리.
    assert CRON._tick_lock.locked()
    CRON._tick_lock.release()


def test_route_concurrency_guard_skips_when_running(monkeypatch):
    # 이전 틱 미완(락 held)이면 새 스레드 안 띄우고 202 skip(중복 스레드 금지).
    monkeypatch.delenv("CRON_SECRET", raising=False)
    import src.pricing.cron as CRON
    called = {"spawn": False}
    monkeypatch.setattr(CRON, "_spawn_background_tick",
                        lambda *a, **k: called.__setitem__("spawn", True))
    CRON._last_tick.clear(); CRON._last_tick.update({"total_sec": 12.3, "drain_sec": 4.0, "pilot_sec": 8.3})
    assert CRON._tick_lock.acquire(blocking=False)               # 이전 틱 진행 중 시뮬레이션
    try:
        from src.order_webhook import app
        r = app.test_client().post("/cron/translate-drain")
        assert r.status_code == 202
        d = r.get_json()
        assert d["skipped"] is True and d["status"] == "already_running"
        assert d["last_tick"]["total_sec"] == 12.3               # 최근 틱 소요 노출
        assert called["spawn"] is False                          # 중복 스레드 안 띄움
    finally:
        CRON._tick_lock.release()


def test_run_full_tick_budget_split_and_releases_lock(monkeypatch):
    # 백그라운드 실작업: 번역 몫 = min(drain_share 20, tick 45 - pilot_min 5)=20, 파일럿엔 나머지. 락 해제 보장.
    for v in ("CRON_TICK_BUDGET_SEC", "TRANSLATE_DRAIN_BUDGET_SEC"):
        monkeypatch.delenv(v, raising=False)
    import src.seller_console.translate_worker as TW
    import src.pricing.cron as CRON
    seen = {}
    def _fake_drain(limit=10, time_budget_sec=None):
        seen["drain_budget"] = time_budget_sec
        return {"ok": True, "processed": 3, "remaining": 97, "budget_exhausted": True}
    def _fake_pilot(chunk=3, time_budget_sec=None):
        seen["pilot_budget"] = time_budget_sec
        return {"revived": 1, "backfilled": 2, "remaining_pending": 5, "budget_exhausted": False}
    monkeypatch.setattr(TW, "drain_once", _fake_drain)
    monkeypatch.setattr(CRON, "_run_pilot_finish_tick", _fake_pilot)
    from src.order_webhook import app
    CRON._tick_lock.acquire(blocking=False)                     # 라우트가 잡은 상태 시뮬레이션
    out = CRON._run_full_tick(app, limit=10, pilot_chunk=3, tick_budget=45.0)
    assert seen["drain_budget"] == 20.0 and seen["pilot_budget"] > 5.0
    assert out["drain"]["processed"] == 3 and out["pilot"]["revived"] == 1
    assert "total_sec" in out and "drain_sec" in out
    assert not CRON._tick_lock.locked()                         # finally에서 락 해제(무한 점유 방지)
    assert CRON._last_tick.get("total_sec") is not None         # 최근 틱 기록(로그/진단)
