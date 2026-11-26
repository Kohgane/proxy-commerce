"""오너 11-25 감독 2(통과 기준 2번) — 타오바오 공유 23건(09-28~10-28)이 **사진 0 · 보강 시도 0 · 차단 사유 0**으로 멈춘 근원과 수리.

근원(코드): ① 자동 보강이 메모리 스레드 하나뿐 — 배포·재시작에 죽으면 기록도 사유도 없음 ② 공유 초안 입구 셋 중 하나만 kick
③ 꺼져 있으면 조용히 False. 수리: 줄(`app_state`)에 먼저 세움 · 틱이 남은 줄 돌림 · 입구 하나(`collect_from_share_text`)에서 kick ·
꺼져 있으면 카드에 「꺼짐」 · 관리자 재보강(기본 목록만).
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def state(monkeypatch):
    store = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: store.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: store.__setitem__(k, v))
    return store


@pytest.fixture
def no_thread(monkeypatch):
    import src.services.taobao_auto as T
    started = []

    class _T:
        def __init__(self, target, args, daemon):
            started.append(args)

        def start(self):
            pass
    monkeypatch.setattr(T.threading, "Thread", _T)
    return started


def _draft(seller="u-tb", url="https://item.taobao.com/item.htm?id=744111222333", extra=None):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "접이식 수납함", "images": [], "mode": "share", "enrich_state": "pending"}
    ex.update(extra or {})
    return S.append(source="share", url=url, title="접이식 수납함", price="", currency="CNY", image="", seller_id=seller, extra=ex)


def test_kick_queues_before_thread_so_a_restart_does_not_lose_it(state, no_thread, monkeypatch):
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    from src.services import taobao_auto as T
    assert T.kick("u1", "i1") is True
    assert [r["item_id"] for r in T.queue_rows()] == ["i1"] and no_thread == [("u1", "i1")]


def test_drain_runs_left_over_rows_and_dequeues(state, monkeypatch):
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    from src.services import taobao_auto as T
    ran = []
    monkeypatch.setattr(T, "run", lambda u, i, **k: ran.append((u, i)) or {"state": "done"})
    T.enqueue("u1", "old")
    rows = T.queue_rows()
    rows[0]["at"] = "2026-11-01T00:00:00+00:00"                      # 스레드가 죽어 남은 줄
    T._queue_save(rows)
    T.enqueue("u2", "fresh")                                        # 방금 세운 줄(스레드가 돌고 있을 것) — 건드리지 않는다
    out = T.drain()
    assert ran == [("u1", "old")] and out["ran"] == 1
    assert [r["item_id"] for r in T.queue_rows()] == ["fresh"]


def test_off_is_recorded_on_the_card_not_silent(state, monkeypatch):
    monkeypatch.delenv("TAOBAO_DETAIL_PROVIDER", raising=False)
    monkeypatch.setenv("TAOBAO_MTOP_AUTO", "0")
    from src.services import taobao_auto as T
    from src.seller_console import collect_history_store as S
    iid = _draft()
    assert T.kick("u-tb", iid) is False
    ae = json.loads(S.get(iid, seller_ids={"u-tb"})["extra_json"])["auto_enrich"]
    assert ae["state"] == "off" and "꺼져 있어요" in ae["reason"]
    assert T.queue_rows() == []


@pytest.mark.parametrize("entry", ["collect_input", "collect_one_url_short", "share_text_direct"])
def test_every_entry_starts_auto_fill(entry, state, no_thread, monkeypatch):
    """입구가 어디든 타오바오 초안이면 보강이 시작된다(예전엔 `collect_input` 하나만)."""
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    import src.collectors.link_diag as L
    monkeypatch.setattr(L, "resolve_short_link", lambda url, timeout=6: {
        "ok": True, "item_id": "744111222999", "price": "", "currency": "", "canonical_url": "https://item.taobao.com/item.htm?id=744111222999",
        "reason": "ok"})
    text = "【淘宝】https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=abc 「折叠收纳盒 大号」"
    if entry == "collect_input":
        from src.collectors.share_collect import collect_input
        r = collect_input(text, seller_id="u-tb", source="share", translate=False)
    elif entry == "collect_one_url_short":
        from src.api.extension_api import collect_one_url
        r = collect_one_url("https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=abc", seller_id="u-tb", source="bulk")
    else:
        from src.collectors.share_collect import collect_from_share_text
        r = collect_from_share_text(text, seller_id="u-tb", source="share_text", translate=False)
    assert r["ok"]
    assert len(no_thread) == 1 and no_thread[0][0] == "u-tb"
    assert [q["item_id"] for q in __import__("src.services.taobao_auto", fromlist=["x"]).queue_rows()] == [no_thread[0][1]]


def test_admin_reenrich_lists_then_queues_only_never_tried(state, monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    from src.order_webhook import app
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    stuck = _draft(seller="u-a", url="https://item.taobao.com/item.htm?id=111111111111")
    tried = _draft(seller="u-a", url="https://item.taobao.com/item.htm?id=222222222222", extra={"auto_enrich": {"state": "manual"}})
    filled = _draft(seller="u-a", url="https://item.taobao.com/item.htm?id=333333333333", extra={"images": ["https://img/a.jpg"]})
    c = app.test_client()
    d = c.get("/seller/admin/taobao-reenrich").get_json()
    ids = [r["item_id"] for r in d["rows"]]
    assert d["dry_run"] and stuck in ids and tried not in ids and filled not in ids and d["queued"] == 0
    from src.services import taobao_auto as T
    assert T.queue_rows() == []                                     # 목록만 — 아무것도 안 세움
    d2 = c.post("/seller/admin/taobao-reenrich", json={"run": True}).get_json()
    assert d2["queued"] >= 1 and stuck in [r["item_id"] for r in T.queue_rows()]


def test_admin_reenrich_is_admin_only(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    assert app.test_client().get("/seller/admin/taobao-reenrich").status_code == 403
