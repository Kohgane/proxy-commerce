"""P0-운영 추가 1(오너 2026-10-23) — 강제 종료(os._exit) 뒤 남는 「running」을 다음 부팅이 닫고 안전한 것만 다시 넣는다."""
import time


def test_dead_process_leftovers_are_closed_and_only_safe_lines_requeued(monkeypatch):
    from src.db import image_translate_queue_pg as st
    from src.seller_console import views as V
    from src.services import oneshot_ops as O
    from src.services import restart_recovery as R
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    monkeypatch.setattr("src.utils.instance.holder", lambda: "srv-new:41")
    now = time.time()
    old = now - R.inflight_stale_sec() - 60

    def at(ts):
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts, timezone.utc).isoformat()

    # 옛 인스턴스(죽음)가 남긴 진행 기록: 시작 못 한 줄 · 돌던 사전검증 · 돌던 등록 · 이미 한 번 다시 돈 사전검증
    st.state_set(O.INFLIGHT_PREFIX + "srv-old:35", {"holder": "srv-old:35", "at": at(old), "rows": [
        {"op": "check_item", "item_id": "aaaa1111", "markets": ["coupang"], "_state": "done"},
        {"op": "prevalidate", "item_id": "bbbb2222", "markets": ["coupang"], "_state": "running"},
        {"op": "register", "item_id": "cccc3333", "markets": ["coupang"], "_state": "running"},
        {"op": "prevalidate", "item_id": "dddd4444", "markets": ["naver"], "_state": "running", "restarts": 1},
        {"op": "owner_decision", "item_id": "eeee5555", "markets": ["naver"], "_state": "pending"},
    ]})
    st.state_set(O.INFLIGHT_PREFIX + "srv-mid:36", {"holder": "srv-mid:36", "at": at(now - 30), "rows": [   # 아직 돌 수 있음
        {"op": "register", "item_id": "ffff6666", "markets": ["coupang"], "_state": "running"}]})
    # 일회성 줄이 띄운 사전검증 잡(옛 인스턴스) — 판정 창 지남 · 쿠팡만 도착 / 화면에서 띄운 잡(창 안) — 그대로
    st.state_set(V._PV_JOB_KEY + "job-old", {"state": "running", "queued": True, "holder": "srv-old:35",
                                              "started_ts": now - R.pv_window_sec() - 5, "markets": ["coupang", "naver"],
                                              "results": {"coupang": {"market": "coupang", "ok": True}},
                                              "oneshot": {"op": "check_item", "item_id": "gggg7777", "markets": ["coupang", "naver"]}})
    st.state_set(V._PV_JOB_KEY + "job-fresh", {"state": "running", "holder": "srv-old:35", "started_ts": now - 10,
                                                "markets": ["coupang"], "results": {}})

    out = R.sweep(now=now)

    q = {(r["op"], r["item_id"]): r for r in O.queue_rows()}
    assert set(q) == {("prevalidate", "bbbb2222"), ("owner_decision", "eeee5555"), ("check_item", "gggg7777")}
    assert q[("prevalidate", "bbbb2222")]["restarts"] == 1 and "_state" not in q[("prevalidate", "bbbb2222")]
    assert "restarts" not in q[("owner_decision", "eeee5555")]                     # 시작 못 한 줄은 횟수 안 셈
    assert q[("check_item", "gggg7777")]["restarts"] == 1
    gone = {(r["op"], r["item_id"]) for r in st.state_get(O.INTERRUPTED_KEY)["rows"]}
    assert gone == {("register", "cccc3333"), ("prevalidate", "dddd4444")}         # 등록은 다시 안 넣음 · 두 번째 끊김도
    assert st.state_get(O.INFLIGHT_PREFIX + "srv-old:35") == {}
    assert st.state_get(O.INFLIGHT_PREFIX + "srv-mid:36")["rows"][0]["item_id"] == "ffff6666"
    job = st.state_get(V._PV_JOB_KEY + "job-old")
    assert job["state"] == "done" and job["interrupted"] and job["results"]["coupang"]["ok"] is True
    assert job["results"]["naver"]["transport"] == "interrupted" and "서버가 다시 시작돼" in job["results"]["naver"]["message"]
    assert st.state_get(V._PV_JOB_KEY + "job-fresh")["state"] == "running"
    assert out["oneshot"] == {"records": 1, "requeued": 2, "interrupted": 2} and out["prevalidate"] == {"closed": 1, "requeued": 1}

    assert R.sweep(now=now + 5)["oneshot"]["records"] == 0                         # 두 번째 스윕은 아무것도 안 한다
    assert len(O.queue_rows()) == 3
