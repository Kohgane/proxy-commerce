"""Y15 순찰 57(오너 2026-10-23) — 요청 샘플 DB 원자 카운터 · 큐 넣기/꺼내기 원자화 · Z9 공유 판정 user_id 통일 + 403 힌트."""
import threading


def _mem_store(monkeypatch):
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    return st


def test_queue_insert_and_take_never_lose_rows_under_concurrency(monkeypatch):
    st = _mem_store(monkeypatch)
    from src.services import oneshot_ops as O
    monkeypatch.setattr(O, "_run", lambda row: {"ok": True})
    monkeypatch.setattr(O, "_job_env", lambda row: __import__("contextlib").nullcontext())
    barrier = threading.Barrier(8)

    def put(k):
        barrier.wait()
        for i in range(25):
            O.enqueue({"op": "review_status", "item_id": f"{k}-{i}", "market": "coupang"})

    ts = [threading.Thread(target=put, args=(k,)) for k in range(8)]
    for t in ts:
        t.start()
    taken = 0
    while any(t.is_alive() for t in ts) or O.queue_rows():         # 넣는 동안에도 꺼낸다
        taken += O.drain()["picked"]
    assert taken == 200 and O.queue_rows() == []                    # 넣은 200줄 = 꺼낸 200줄
    assert O.enqueue({"op": "prevalidate", "item_id": "x"}) and not O.enqueue({"op": "prevalidate", "item_id": "x"})
    assert st.state_incr("c") == 1 and st.state_incr("c", 9) == 10


def test_request_sample_counter_lives_in_db_and_survives_restart(monkeypatch):
    st = _mem_store(monkeypatch)
    import src.order_webhook as W
    from src.utils import render_worker as RW
    monkeypatch.setenv("TICK_PROBE", "1")                         # conftest는 끈다 — 이 테스트만 켠다
    monkeypatch.setattr(W, "_REQ_PROBE_EVERY", 100)
    monkeypatch.setattr(W, "_REQ_PROBE_FLUSH_N", 10)
    monkeypatch.setattr(W, "_REQ_PROBE", {"pending": 0, "flushed_at": __import__("time").monotonic(), "lock": threading.Lock()})
    c = W.app.test_client()
    for _ in range(95):
        c.get("/health")
    assert st.state_get(W.REQ_PROBE_KEY)["n"] == 90                 # 10개마다 DB에 더한다(5개는 아직 손에)
    assert not [r for r in (st.state_get(RW.TICKS_KEY) or {}).get("rows", []) if r["kind"] == "req"]
    monkeypatch.setattr(W, "_REQ_PROBE", {"pending": 0, "flushed_at": __import__("time").monotonic(), "lock": threading.Lock()})   # 재시작: 손에 든 5개는 잃는다
    for _ in range(10):
        c.get("/nope-scan")
    rows = [r for r in st.state_get(RW.TICKS_KEY)["rows"] if r["kind"] == "req"]
    assert st.state_get(W.REQ_PROBE_KEY)["n"] == 100 and len(rows) == 1
    assert rows[0]["n"] == 100 and rows[0]["endpoint"] == "path:/nope-scan" and rows[0]["status"] == 404


def test_shared_is_identity_not_session_role_and_403_says_why(monkeypatch):
    from src.order_webhook import app
    from src.seller_console import market_credentials as mc
    monkeypatch.setattr(mc, "_shared_cache", {})
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    monkeypatch.delenv("FAMILY_EMAILS", raising=False)
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"], s["user_email"], s["user_role"] = "36ba2852-aaaa-bbbb", "me@example.com", "admin"
        r = c.get("/seller/wholesale/tiers")
        page = r.get_data(as_text=True)
        assert r.status_code == 403 and "앞 8자리 36ba2852" in page and "ADMIN_USER_IDS" not in page
        js = c.get("/seller/messaging/log").get_json()
        assert js["hint"].startswith("이 화면은 로그인 계정 번호로 판정해요")
        monkeypatch.setenv("ADMIN_USER_IDS", "x, 36BA2852-aaaa-bbbb")
        assert c.get("/seller/wholesale/tiers").status_code == 200          # 목록에 넣으면 role 상관없이 열린다
    monkeypatch.delenv("ADMIN_USER_IDS")
    monkeypatch.setenv("FAMILY_EMAILS", "fam@example.com")
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"], s["user_email"], s["user_role"] = "fam-1", "fam@example.com", "seller"
        assert c.get("/seller/wholesale/tiers").status_code == 200          # 가족 로그인 이메일


import os  # noqa: E402

import pytest  # noqa: E402


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="PG 레인 전용")
def test_state_update_serializes_writers_on_postgres():
    """`FOR UPDATE` 경로 — A가 행을 잡은 채 쉬는 동안 B가 쓰면 B는 기다렸다가 A 뒤에 붙는다(예전 읽고-덧쓰기는 B를 덮었다)."""
    import time
    from src.db import image_translate_queue_pg as st
    key = "p57:test:queue"
    st.state_set(key, {"rows": []})
    try:
        def slow_a(cur):
            time.sleep(0.5)
            return {"rows": list(cur.get("rows") or []) + ["A"]}

        ta = threading.Thread(target=lambda: st.state_update(key, slow_a))
        ta.start()
        time.sleep(0.1)
        st.state_update(key, lambda cur: {"rows": list(cur.get("rows") or []) + ["B"]})
        ta.join()
        assert st.state_get(key)["rows"] == ["A", "B"]
        st.state_delete(key)
        assert st.state_incr(key, 3) == 3 and st.state_incr(key) == 4
    finally:
        st.state_delete(key)
