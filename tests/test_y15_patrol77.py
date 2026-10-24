"""Y15 순찰 77(오너 2026-10-24) — 화면 등록을 잡으로(202 + 폴링) · 요청 스레드가 전부 묶이면 워커를 내린다 · quiet 줄에 처리 중 요청·스택 맨 줄."""
import threading
import time


def _mem(monkeypatch):
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    return st


def _hold_request(path, started, release):
    """요청 스레드 하나가 `path`를 처리하다 멈춘 모양(stall_guard에 들어간 채 대기)."""
    from src.utils import stall_guard as SG

    def _run():
        SG.begin(path)
        started.set()
        release.wait(5)
        SG.end()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def test_quiet_row_names_the_stuck_request_and_its_stack_top(monkeypatch):
    _mem(monkeypatch)
    from src.utils import restart_log as R
    monkeypatch.setenv("HTTP_QUIET_MIN", "10")
    started, release = threading.Event(), threading.Event()
    t = _hold_request("/seller/collect/upload", started, release)
    try:
        assert started.wait(2)
        R.touch_request()
        exits = []
        row = R.check_quiet(R._LAST_REQ["at"] + 26 * 60, exit_fn=exits.append)
        mine = [a for a in row["active"] if a["path"] == "/seller/collect/upload"]
        assert mine and "wait" in mine[0]["top"]                     # 스택 맨 줄 = 멈춘 자리(release.wait)
        assert row["http_busy"] >= 1 and row["threads_cfg"] == 8 and exits == []     # 8개 중 1개만 묶임 = 내리지 않음
        assert R.rows()[-1]["kind"] == "quiet"
    finally:
        release.set()
        t.join(2)


def test_all_request_threads_stuck_exits_this_worker(monkeypatch):
    _mem(monkeypatch)
    from src.utils import restart_log as R
    monkeypatch.setenv("GUNICORN_THREADS", "2")
    started = [threading.Event(), threading.Event()]
    release = threading.Event()
    ts = [_hold_request(p, e, release) for p, e in zip(("/seller/collect/upload", "/health"), started)]
    try:
        assert all(e.wait(2) for e in started)
        R.touch_request()
        exits = []
        row = R.check_quiet(R._LAST_REQ["at"] + 11 * 60, exit_fn=exits.append)
        assert row["exit"] is True and len(exits) == 1
        kinds = [(r["kind"], r.get("reason")) for r in R.rows()]
        assert kinds[-2:] == [("quiet", None), ("exit", "요청 스레드 전부 묶임")]
        monkeypatch.setenv("QUIET_EXIT", "0")                           # 끄면 적기만
        R.touch_request()
        exits.clear()
        assert "exit" not in R.check_quiet(R._LAST_REQ["at"] + 11 * 60, exit_fn=exits.append) and exits == []
    finally:
        release.set()
        for t in ts:
            t.join(2)


def _poll(c, url, sec=3.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < sec:
        j = c.get(url).get_json()
        if j.get("state") in ("done", "interrupted"):
            return j
        time.sleep(0.05)
    raise AssertionError("잡이 끝나지 않음")


def test_screen_upload_returns_202_then_the_same_body_and_status(monkeypatch):
    _mem(monkeypatch)
    from flask import jsonify
    from src.order_webhook import app
    from src.seller_console import views as V
    seen = []

    def run(data):
        seen.append((threading.current_thread().name, data))
        if data.get("confirm_duplicate"):
            return jsonify({"ok": True, "result": {"results": [{"market": "coupang:gogane", "success": True}]}})
        return jsonify({"ok": False, "needs_dup_confirm": True, "error": "이미 등록된 마켓이 있어요"}), 409
    monkeypatch.setattr(V, "_collect_upload_run", run)
    app.config["TESTING"] = True
    with app.test_client() as c:
        r = c.post("/seller/collect/upload", json={"async": True, "product": {"title": "x"}, "markets": ["coupang:gogane"]})
        assert r.status_code == 202 and r.get_json()["poll"].startswith("/seller/collect/upload/job/")
        j = _poll(c, r.get_json()["poll"])
        assert j["http_status"] == 409 and j["body"]["needs_dup_confirm"] is True     # 409 확인 창도 예전 그대로
        r2 = c.post("/seller/collect/upload", json={"async": True, "product": {"title": "x"}, "markets": ["coupang:gogane"],
                                                    "confirm_duplicate": True})
        j2 = _poll(c, r2.get_json()["poll"])
        assert j2["http_status"] == 200 and j2["body"]["result"]["results"][0]["success"] is True
    assert all(name.startswith("upload-job-") for name, _ in seen)              # 몸통은 잡 스레드에서
    assert all("async" not in d for _, d in seen)


def test_sync_paths_stay_sync_oneshot_and_no_flag(monkeypatch):
    _mem(monkeypatch)
    from flask import jsonify
    from src.order_webhook import app
    from src.seller_console import views as V
    from src.services import oneshot_ops as O
    monkeypatch.setattr(V, "_collect_upload_run", lambda data: jsonify({"ok": True, "result": {"results": []}, "sync": True}))
    app.config["TESTING"] = True
    with app.test_client() as c:
        assert c.post("/seller/collect/upload", json={"product": {"t": 1}, "markets": ["a"]}).get_json()["sync"] is True
    tok = O._CURRENT_ROW.set({"op": "register"})
    try:
        with app.test_request_context("/seller/collect/upload", method="POST", json={"async": True, "product": {"t": 1}}):
            resp = V.collect_upload()
        assert (resp if not isinstance(resp, tuple) else resp[0]).get_json()["sync"] is True   # 일회성 줄 등록은 끝까지 동기
    finally:
        O._CURRENT_ROW.reset(tok)


def test_other_seller_cannot_read_the_job(monkeypatch):
    st = _mem(monkeypatch)
    from src.order_webhook import app
    from src.seller_console import views as V
    st.state_set(V._UP_JOB_KEY + "abc", {"state": "done", "owner": "someone-else", "body": {"ok": True}})
    app.config["TESTING"] = True
    with app.test_client() as c:
        assert c.get("/seller/collect/upload/job/abc").status_code == 404


def test_restart_closes_old_upload_jobs_without_requeue(monkeypatch):
    st = _mem(monkeypatch)
    from src.seller_console import views as V
    from src.services import restart_recovery as RR
    from src.utils.instance import holder
    now = time.time()
    st.state_set(V._UP_JOB_KEY + "old", {"state": "running", "holder": "dead:1", "started_ts": now - 900, "owner": "o"})
    st.state_set(V._UP_JOB_KEY + "new", {"state": "running", "holder": "dead:1", "started_ts": now - 30, "owner": "o"})
    st.state_set(V._UP_JOB_KEY + "mine", {"state": "running", "holder": holder(), "started_ts": now - 900, "owner": "o"})
    out = RR._sweep_upload(now, holder())
    assert out == {"closed": 1}
    old = st.state_get(V._UP_JOB_KEY + "old")
    assert old["state"] == "interrupted" and "중복" in old["body"]["error"] and old["http_status"] == 503
    assert st.state_get(V._UP_JOB_KEY + "new")["state"] == "running" and st.state_get(V._UP_JOB_KEY + "mine")["state"] == "running"


def test_callers_use_the_job_helper_and_gunicorn_values():
    import os
    root = os.path.join(os.path.dirname(__file__), "..")
    js = open(os.path.join(root, "src/seller_console/static/seller.js"), encoding="utf-8").read()
    assert "window.kgpUploadJob = async function" in js and "async: true" in js
    for f in ("collect_preview.html", "_m5_flow.html", "manual_collect.html"):
        assert "kgpUploadJob" in open(os.path.join(root, "src/seller_console/templates", f), encoding="utf-8").read(), f
    import importlib.util
    spec = importlib.util.spec_from_file_location("gconf_p77", os.path.join(root, "gunicorn.conf.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    assert g.threads >= 8 and g.timeout == 120 and g.worker_class == "gthread"


def test_browser_helper_polls_the_job_and_returns_the_same_body(monkeypatch):
    """실브라우저: seller.js `kgpUploadJob` → POST 202 → 3초 뒤 폴링 → 예전 동기 응답과 같은 본문(확인 창 키 그대로)."""
    import os
    import shutil
    import pytest
    if not (shutil.which("node") or os.path.exists("/opt/pw-browsers/chromium")):
        pytest.skip("브라우저 없음")
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from flask import jsonify
    from src.order_webhook import app
    from src.seller_console import views as V
    _mem(monkeypatch)
    monkeypatch.setattr(V, "_collect_upload_run", lambda data: (time.sleep(0.2), (jsonify(
        {"ok": False, "needs_dup_confirm": True, "error": "이미 등록된 마켓이 있어요"}), 409))[1])
    app.config["TESTING"] = True
    c = app.test_client()
    js = open("src/seller_console/static/seller.js", encoding="utf-8").read()
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = b.new_page()

        def handle(route):
            req = route.request
            path = req.url.split("kgp.test", 1)[1]
            if path == "/":
                route.fulfill(status=200, content_type="text/html", body="<html><body><script src='/s.js'></script></body></html>")
            elif path == "/s.js":
                route.fulfill(status=200, content_type="application/javascript", body=js)
            elif req.method == "POST":
                r = c.post(path, data=req.post_data, content_type="application/json")
                route.fulfill(status=r.status_code, content_type="application/json", body=r.get_data(as_text=True))
            else:
                r = c.get(path)
                route.fulfill(status=r.status_code, content_type="application/json", body=r.get_data(as_text=True))
        pg.route("**/*", handle)
        pg.goto("http://kgp.test/")
        out = pg.evaluate("kgpUploadJob({product: {title: 'x'}, markets: ['coupang:gogane'], item_id: 'i1'})")
        b.close()
    assert out["needs_dup_confirm"] is True and out["_status"] == 409 and "이미 등록된" in out["error"]
