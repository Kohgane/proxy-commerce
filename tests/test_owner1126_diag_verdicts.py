"""오너 11-26 진단 캡처 판정 2·3·4 — 계약.

2 셰고가: 키-스토어 대조는 **채널번호로**(고코스모스 키 → 실제 「나의코스모스(102783356)」는 정상) · 한도 옆 「판매중지 n」 + 한 줄 설명 ·
  판매중지 중 우리 기록(등록·「이 마켓에서 내리기」)에 있는 만큼만 · 나머지는 「우리 기록에 없음」
3 관리자 진단 3화면: 폰 브라우저 = 판정 한 줄 + 한글 표 · `?raw=1`·스크립트 = JSON 그대로
4 타오바오 재보강: 「N건 다시 가져오기」 두 번 눌러 확인 · 예상 비용 · 진행 n/N · 성공/실패 사유 표 · 중복·시험 계정 구분(대상 제외) · 오너 탭으로만
"""
from __future__ import annotations

import json

import pytest

HTML = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


@pytest.fixture
def state(monkeypatch):
    s = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: s.__setitem__(k, v))
    return s


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["email"], s["user_role"] = "own", "owner@example.com", "admin"
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    return c


# ── 2 ──────────────────────────────────────────────────────────────────────

def test_key_match_by_channel_number_not_label():
    from src.services.admin_diag import key_match
    ok = key_match("gocosmos", [{"name": "나의코스모스", "no": "102783356"}], "102783356", "고코스모스")
    assert ok["state"] == "ok" and "키 정상" in ok["line"]                      # 이름이 달라도 번호가 같으면 정상(오경보 수리)
    bad = key_match("gocosmos", [{"name": "셰고가", "no": "555"}], "102783356", "고코스모스")
    assert bad["state"] == "mismatch" and "102783356" in bad["line"]
    assert key_match("chezgoga", [{"name": "셰고가", "no": "777"}], "", "셰고가")["state"] == "unpinned"   # 번호 모르면 판정 안 함


def test_gocosmos_channel_number_is_pinned():
    from src.seller_console import smartstore_routing as R
    R.reset_cache()
    assert R.store_channel_no("gocosmos") == "102783356"


def test_limit_state_shows_suspended_with_explain(monkeypatch):
    from src.seller_console import smartstore_routing as R
    monkeypatch.setattr(R, "probe", lambda st, force=False: {"ok": True, "count": 403, "suspended": 1679, "state": "ok"})
    ls = R.limit_state("chezgoga")
    assert ls["text"].endswith("403/1,000") and ls["suspended_text"] == "판매중지 1,679"
    assert "한도에 안 들어가요" in ls["explain"] and "1,000은 판매중·판매대기·품절만" in ls["explain"]


def test_our_store_records_counts_only_what_we_did(state):
    from src.seller_console import collect_history_store as S
    from src.services.admin_diag import our_store_records
    a = S.append(source="share", url="https://x/1", title="a", price="1", currency="USD", image="", seller_id="sx1",
                 extra={"uploaded": [{"market": "smartstore:chezgoga", "product_id": "1"}],
                        "takedowns": [{"market": "smartstore:chezgoga", "ok": True}, {"market": "smartstore:chezgoga", "ok": False}]})
    b = S.append(source="share", url="https://x/2", title="b", price="1", currency="USD", image="", seller_id="sx1",
                 extra={"uploaded": [{"market": "coupang:gogane", "product_id": "2"}]})
    r = our_store_records()["chezgoga"]
    assert r["registered"] >= 1 and r["taken_down_ok"] >= 1 and r["taken_down_fail"] >= 1
    S.delete([a, b], seller_id="sx1")


# ── 3 ──────────────────────────────────────────────────────────────────────

def _fake_store_audit(nos=()):
    return {"stores": [{"store": "gocosmos", "label": "고코스모스", "token": True, "channels": ["나의코스모스 (102783356)"],
                        "counts": {"SALE": 400, "WAIT": 2, "OUTOFSTOCK": 1, "SUSPENSION": 1679, "CLOSE": 0, "PROHIBITION": 1},
                        "limit_count": 403, "key_match": {"state": "ok", "line": "키 정상 — 채널 102783356"}}],
            "mismatch": [], "products": {}, "our_records": {"gocosmos": {"registered": 12, "taken_down_ok": 3, "taken_down_fail": 0}}}


def test_stores_page_is_readable_table_and_raw_is_json(admin, monkeypatch):
    import src.services.admin_diag as D
    monkeypatch.setattr(D, "store_audit", _fake_store_audit)
    h = admin.get("/seller/admin/diag/stores", headers=HTML).get_data(as_text=True)
    assert 'data-role="dg-verdict"' in h and "키 정상 1/1" in h and "판매중지" in h and "1,679" in h and "403/1,000" in h
    assert "우리 기록: 등록 12 · 우리가 내림 3" in h and "1,676건은 <strong>우리 기록에 없음</strong>" in h
    assert "\\u" not in h
    d = admin.get("/seller/admin/diag/stores?raw=1", headers=HTML).get_json()
    assert d["ok"] and d["stores"][0]["limit_count"] == 403
    assert admin.get("/seller/admin/diag/stores").get_json()["ok"]                   # Accept 없는 스크립트는 JSON


def test_item_page_verdict_counts_usable_photos(admin, monkeypatch):
    import src.services.admin_diag as D
    monkeypatch.setattr(D, "item_audit", lambda no: {"market_no": no, "rows": [{
        "id": "b6809323abcd", "source": "share", "url": "https://www.amazon.com/dp/B0D", "raw_url": "https://a.co/d/00NkaQHC",
        "mode": "share", "enrich_state": "", "images_stored": 0, "detail_images": 0, "title": "tomtoc", "skus": 0, "options": [],
        "images": [{"url": "https://m.media-amazon.com/images/I/31a._AC_US40_.jpg", "w": 40, "h": 40},
                   {"url": "https://m.media-amazon.com/images/I/71a._AC_SX522_.jpg", "w": 522, "h": 927},
                   {"url": "https://m.media-amazon.com/images/S/sash/b.svg", "w": None, "h": None, "why": "svg"}]}]})
    h = admin.get("/seller/admin/diag/item/13894618263", headers=HTML).get_data(as_text=True)
    assert "쓸 만한 사진 1/3" in h and h.count('data-role="dg-img"') == 3 and "522×927" in h and "못 잼 svg" in h


# ── 4 ──────────────────────────────────────────────────────────────────────

def _tb_rows():
    from src.seller_console import collect_history_store as S
    ids = []
    for sid, num in (("u1", "711"), ("u1", "712"), ("u2", "711"), ("dev", "713")):
        ids.append((sid, S.append(source="share", url=f"https://item.taobao.com/item.htm?id={num}000000001", title=f"t{num}",
                                  price="", currency="CNY", image="", seller_id=sid, extra={"images": [], "item_id_taobao": f"{num}000000001"})))
    return ids


def test_reenrich_page_marks_dup_and_test_and_shows_cost(admin, state, monkeypatch):
    from src.services import taobao_auto as TA
    monkeypatch.setattr(TA, "enabled", lambda: True)
    monkeypatch.setattr(TA, "effective_route", lambda: "onebound")
    made = _tb_rows()
    try:
        d = admin.get("/seller/admin/taobao-reenrich").get_json()
        mine = [r for r in d["rows"] if r["item_id"] in {i for _, i in made}]
        assert len(mine) == 4
        assert sum(1 for r in mine if r["dup_of"]) == 1 and sum(1 for r in mine if r["test"]) == 1
        elig = [r for r in mine if r["eligible"]]
        assert len(elig) == 2 and "0.023元" in d["estimate"]["line"]
        h = admin.get("/seller/admin/taobao-reenrich", headers=HTML).get_data(as_text=True)
        assert f'{d["eligible"]}건 다시 가져오기' in h and 'data-role="dg-dup"' in h and 'data-role="dg-test"' in h and "예상 비용" in h
        assert "한 번 더 누르면" in h                                              # 두 번 눌러 확인
    finally:
        from src.seller_console import collect_history_store as S
        for sid, i in made:
            S.delete([i], seller_id=sid)


def test_reenrich_batch_needs_matching_count_then_runs_with_progress(admin, state, monkeypatch):
    from src.services import taobao_auto as TA
    from src.services import taobao_reenrich_batch as B
    from src.utils import bg_job
    monkeypatch.setattr(TA, "enabled", lambda: True)
    monkeypatch.setattr(TA, "effective_route", lambda: "mtop")
    calls = []
    monkeypatch.setattr(TA, "run", lambda uid, iid, src="": calls.append(iid) or ({"state": "done"} if len(calls) % 2 else {"state": "manual", "reason": "로그인 벽"}))
    jobs = []
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (jobs.append(name), fn(), (True, {}))[2])
    made = _tb_rows()
    try:
        n = admin.get("/seller/admin/taobao-reenrich").get_json()["eligible"]
        assert admin.post("/seller/admin/taobao-reenrich", json={"now": True, "confirm": n + 1}).status_code == 409
        assert calls == []
        d = admin.post("/seller/admin/taobao-reenrich", json={"now": True, "confirm": n}).get_json()
        assert d["ok"] and jobs == ["djob:taobao_reenrich:batch"] and len(calls) == n
        p = admin.get("/seller/admin/taobao-reenrich?progress=1").get_json()
        assert p["state"] == "finished" and len(p["done"]) == n and p["ok_count"] == (n + 1) // 2
        assert any((not x["ok"]) and x["reason"] == "로그인 벽" for x in p["done"])
        assert all(x["item_id"] not in {i for s, i in made if s == "dev"} for x in p["done"])   # 시험 계정은 안 돌림
    finally:
        from src.seller_console import collect_history_store as S
        for sid, i in made:
            S.delete([i], seller_id=sid)


def test_reenrich_estimate_mtop_free():
    from src.services.taobao_reenrich_batch import estimate
    assert estimate(27, "mtop")["yuan_max"] == 0 and estimate(27, "onebound")["yuan_min"] == round(27 * 0.023, 3)
