"""Y15 순찰 80(오너 2026-10-24 df0f8a8c) — 스마트스토어 전 상태 상품명 찾기(읽기만) · 등록 줄을 화면 등록 잡 경로로(`reg_job`)."""
import threading


def _mem(monkeypatch):
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    return st


def _pages(*pages):
    calls = []

    def fake(self, method, path, data=None, **kw):
        calls.append(data)
        return pages[min(len(calls), len(pages)) - 1]
    return fake, calls


def test_find_by_name_scans_every_status_and_says_whether_it_finished(monkeypatch):
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as N
    p1 = {"totalElements": 3, "contents": [
        {"originProductNo": 1, "channelProducts": [{"channelProductNo": 11, "name": "[해외직구] 타지 두부 블록 소파", "statusType": "WAIT",
                                                   "regDate": "2026-10-24T10:50:40"}]},
        {"originProductNo": 2, "channelProducts": [{"channelProductNo": 22, "name": "빈티지 흔들의자", "statusType": "SALE"}]},
        {"originProductNo": 3, "channelProducts": [{"channelProductNo": 33, "name": "두부 모양 쿠션", "statusType": "SUSPENSION"}]}]}
    fake, calls = _pages(p1)
    monkeypatch.setattr(N, "_api_request", fake)
    up = N.__new__(N)
    res = up.find_by_name(["두부", "타지"], size=100)
    assert res["complete"] and res["scanned"] == 3 and [r["channel_no"] for r in res["rows"]] == ["11", "33"]
    assert res["rows"][0]["origin_no"] == "1" and res["rows"][0]["status"] == "WAIT"
    assert set(calls[0]["productStatusTypes"]) >= {"WAIT", "SALE", "SUSPENSION", "UNADMISSION", "REJECTION", "CLOSE"}
    # 다 못 훑었으면(쪽 수 상한) complete=False — 「없음」이라 말하지 않을 근거
    fake2, _ = _pages({"totalElements": 500, "contents": [{"channelProducts": [{"name": "x"}]}] * 2})
    monkeypatch.setattr(N, "_api_request", fake2)
    r2 = up.find_by_name(["두부"], size=2, max_pages=2)
    assert r2["complete"] is False and r2["rows"] == []
    fake3, _ = _pages({"error": "HTTP 401"})
    monkeypatch.setattr(N, "_api_request", fake3)
    assert up.find_by_name(["두부"])["ok"] is False


def test_naver_find_op_reports_per_store(monkeypatch):
    from src.services import oneshot_ops as O
    from src.uploaders import naver_uploader as NU

    class Fake:
        def __init__(self, account):
            self.account = account

        def find_by_name(self, words, max_pages=10):
            pages.append(max_pages)
            rows = [{"channel_no": "9", "name": "타지 두부 블록 소파"}] if self.account == "gocosmos" else []
            return {"ok": True, "rows": rows, "total": 4, "scanned": 4, "complete": True, "error": ""}
    pages = []
    monkeypatch.setattr(NU, "NaverSmartStoreUploader", Fake)
    res = O._run({"op": "naver_find", "item_id": "", "words": ["두부", "타지"]})
    assert res["found"] == 1 and [s["store"] for s in res["stores"]] == ["chezgoga", "gocosmos"]
    assert all(s["complete"] for s in res["stores"]) and pages == [10, 10]
    # 10-24 실측: 1,466·1,187개를 10쪽(1,000)으로 다 못 훑었다 — 줄에서 늘리되 상한 30
    O._run({"op": "naver_find", "item_id": "", "words": ["두부"], "max_pages": 20})
    O._run({"op": "naver_find", "item_id": "", "words": ["두부"], "max_pages": 99})
    assert pages[2:] == [20, 20, 30, 30]


def test_register_row_can_go_through_the_screen_job_and_measures_reg_job(monkeypatch):
    _mem(monkeypatch)
    from flask import jsonify
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    from src.seller_console import views as V
    from src.seller_console import product_builder as PB
    from src.utils import render_worker as RW
    from src.utils import rss
    monkeypatch.setenv("MEMPROBE", "1")
    monkeypatch.setattr(O, "REG_JOB_POLL_SEC", 0.02)
    monkeypatch.setattr(D, "_item", lambda iid: ({"id": "df0f8a8c-73a3", "extra_json": "{}"}, "owner-1"))
    monkeypatch.setattr(PB, "build_product", lambda item, edits=None, seller_id=None: {"title": "타지 두부 블록 소파"})
    monkeypatch.setattr(rss, "release", lambda reason="": (300, 200))
    seen, recs = [], []
    monkeypatch.setattr(RW, "record", lambda kind, **kw: recs.append(kind))

    def run(data):
        seen.append((threading.current_thread().name, list(data["markets"])))
        V._reg_mem_after(V._reg_mem_before(), data["item_id"], data["markets"])     # 실제 몸통과 같은 자리의 측정
        return jsonify({"ok": True, "result": {"results": [
            {"market": m, "success": True, "external_product_id": "1", "channel_product_no": "2"} for m in data["markets"]]}})
    monkeypatch.setattr(V, "_collect_upload_run", run)
    tok = O._CURRENT_ROW.set({"op": "register"})                           # 일회성 줄 안에서 돈다
    try:
        res = O.register("df0f8a8c", ["smartstore:chezgoga", "smartstore:gocosmos"], via_job=True)
    finally:
        O._CURRENT_ROW.reset(tok)
    assert res["ok"] and [r["market"] for r in res["rows"]] == ["smartstore:chezgoga", "smartstore:gocosmos"]
    assert seen and seen[0][0].startswith("upload-job-") and seen[0][1] == ["smartstore:chezgoga", "smartstore:gocosmos"]
    assert "reg_job" in recs                                               # 잡 안에선 일회성 줄 표시가 지워져 측정된다
