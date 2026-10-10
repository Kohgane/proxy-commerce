"""M8(오너 2026-10-10 22:13 KST 폰 Safari, 플리츠 세트 ae9cee70) — 마켓 상태 팝업 2단 · 네이버 기록 표시 · 쿠팡 PUT brand ·
live-fix 응답 코드 · 쿠팡 상품명 끝 수식어.

증거:
- GET /market-status 200 3608ms(릴레이 2570ms × 직렬) → 망 전환 중 Load failed → 팝업 빈 채로 「본문 다시 보내기」 못 누름
- 등록본 카드 「쿠팡 등록본」 — 쿠팡 2건만, uploaded[]의 셰고가 13803311539 · 고코스모스 13803531537 안 보임
- POST live-fix → 쿠팡 PUT 400 「brandId … GENERIC」(페이로드 brand "") → 우리 응답 502
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.test_u_register_followup import AE9, LIVE, _up_with

UPLOADED = [
    {"market": "coupang:gogane", "account": "gogane", "product_id": "16407690349", "market_label": "쿠팡 — 고가네",
     "external_url": "https://www.coupang.com/vp/products/16407690349", "at": "2026-10-09T07:26:00+00:00"},
    {"market": "coupang:woojoo", "account": "woojoo", "product_id": "16407690777", "market_label": "쿠팡 — 우주대행",
     "external_url": "https://www.coupang.com/vp/products/16407690777", "at": "2026-10-09T07:27:00+00:00"},
    {"market": "smartstore:chezgoga", "account": "chezgoga", "product_id": "13742149801", "channel_product_no": "13803311539",
     "external_url": "https://smartstore.naver.com/chezgoga/products/13803311539", "market_label": "스마트스토어 — 셰고가",
     "at": "2026-10-10T09:09:11+00:00"},
    {"market": "smartstore:gocosmos", "account": "gocosmos", "product_id": "13742400001", "channel_product_no": "13803531537",
     "external_url": "https://smartstore.naver.com/main/products/13803531537", "market_label": "스마트스토어 — 고코스모스",
     "at": "2026-10-10T12:11:00+00:00"},
]


def _item(seller):
    from src.seller_console import collect_history_store as S
    ex = json.loads(json.dumps(AE9))
    ex["uploaded"] = json.loads(json.dumps(UPLOADED))
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=999609404643", seller_id=seller,
                   title=ex["title_ko"], price="168", currency="CNY", extra=ex)
    return iid[0] if isinstance(iid, tuple) else iid


def _client(seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


@pytest.fixture(autouse=True)
def _reset():
    from src.seller_console import listing_status as MS
    MS.reset_cache()
    yield
    MS.reset_cache()


# ── 1. 팝업 2단 ───────────────────────────────────────────────────────────────────────────────

def test_1_db_phase_draws_every_market_without_asking_markets(monkeypatch):
    from src.seller_console import listing_status as MS
    monkeypatch.setattr(MS, "query", lambda *a, **k: (_ for _ in ()).throw(AssertionError("마켓에 물으면 안 됨")))
    iid = _item("m8-db")
    t0 = time.monotonic()
    d = _client("m8-db").get(f"/seller/collect/{iid}/market-status?phase=db").get_json()
    assert d["ok"] and d["phase"] == "db" and (time.monotonic() - t0) < 2
    rows = {r["market"]: r for r in d["rows"]}
    assert set(rows) == {"coupang:gogane", "coupang:woojoo", "smartstore:chezgoga", "smartstore:gocosmos"}
    assert rows["smartstore:chezgoga"]["channel_product_no"] == "13803311539"
    assert rows["smartstore:gocosmos"]["channel_product_no"] == "13803531537"
    assert rows["smartstore:gocosmos"]["product_id"]                               # 「본문 다시 보내기」 재료(원상품번호 — 화면엔 안 씀)
    assert all(r["pending"] for r in d["rows"])
    assert rows["coupang:gogane"]["manage_url"].endswith("16407690349")


def test_1_status_phase_is_parallel(monkeypatch):
    from src.seller_console import listing_status as MS

    def slow(rec):
        time.sleep(0.4)
        return {"sid": rec["product_id"], "state": "approved", "label": "판매중", "error": ""}
    monkeypatch.setattr(MS, "_coupang", slow)
    monkeypatch.setattr(MS, "_naver", slow)
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_price_line_for", lambda item, m: "가장 싼 옵션 기준 — …")
    iid = _item("m8-par")
    t0 = time.monotonic()
    d = _client("m8-par").get(f"/seller/collect/{iid}/market-status?phase=status").get_json()
    took = time.monotonic() - t0
    assert d["ok"] and len(d["rows"]) == 4 and all(r["label"] == "판매중" for r in d["rows"])
    assert took < 1.2, took                                                        # 직렬이면 1.6초
    assert isinstance(d["elapsed_ms"], int)
    assert next(r for r in d["rows"] if r["market"] == "smartstore:gocosmos")["price_line"].startswith("가장 싼")


def test_1_one_slow_market_fails_alone_after_timeout(monkeypatch):
    from src.seller_console import listing_status as MS

    def coupang(rec):
        if rec["market"] == "coupang:woojoo":
            time.sleep(1.5)
        return {"sid": rec["product_id"], "state": "pending", "label": "검토중", "error": ""}
    monkeypatch.setattr(MS, "_coupang", coupang)
    monkeypatch.setattr(MS, "_naver", lambda rec: {"sid": rec["channel_product_no"], "state": "approved", "label": "판매중", "error": ""})
    recs = MS.records({"uploaded": UPLOADED})
    t0 = time.monotonic()
    rows = MS.query_many(recs, timeout=0.5)
    assert time.monotonic() - t0 < 1.2
    by = {r["market"]: r for r in rows}
    assert by["coupang:woojoo"]["label"] == "상태 확인 실패" and "답하지 않았어요" in by["coupang:woojoo"]["error"]
    assert by["coupang:gogane"]["label"] == "검토중" and by["smartstore:chezgoga"]["label"] == "판매중"


def test_1_market_error_text_is_kept_per_row(monkeypatch):
    from src.seller_console import listing_status as MS
    monkeypatch.setattr(MS, "_coupang", lambda rec: {"sid": rec["product_id"], "state": "unknown", "label": "확인 못 함",
                                                    "error": "쿠팡 릴레이 실패 — stage=GET … timeout"})
    monkeypatch.setattr(MS, "_naver", lambda rec: {"sid": "x", "state": "approved", "label": "판매중", "error": ""})
    rows = MS.query_many(MS.records({"uploaded": UPLOADED}))
    assert sum(1 for r in rows if r.get("error")) == 2 and sum(1 for r in rows if r["label"] == "판매중") == 2


def test_1_popup_script_two_phase_and_retry():
    t = Path("src/seller_console/templates/_market_status.html").read_text(encoding="utf-8")
    assert "msUrl('db')" in t and "msUrl('status')" in t
    assert 'data-role="mst-retry"' in t and "다시 시도" in t
    assert "mst-status-fail" in t and "swapRow" in t
    assert "dlg.close" in t and "retryLine('mst-error'" in t     # 실패해도 팝업은 닫지 않고 그 안에 한 줄


# ── 2. 마켓 등록본 ─────────────────────────────────────────────────────────────────────────────

def test_2_desktop_card_lists_every_market_with_channel_numbers():
    iid = _item("m8-card")
    h = _client("m8-card").get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    assert "마켓 등록본" in h and "쿠팡 등록본</div>" not in h
    for no in ("16407690349", "16407690777", "13803311539", "13803531537"):
        assert no in h
    card = h[h.index('data-role="cp-live"'):h.index('id="cpLiveOut"')]
    assert "13742149801" not in card and "13742400001" not in card                 # 네이버 원상품번호는 카드에 안 씀
    assert card.count('data-role="ml-row"') == 4


def test_2_phone_card_lists_every_market():
    iid = _item("m8-phone")
    h = _client("m8-phone").get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-ml"' in h and "마켓 등록본" in h
    assert "13803311539" in h and "13803531537" in h and h.count('data-role="ml-row"') == 4


# ── 3·4. 쿠팡 PUT brand · live-fix 응답 코드 ─────────────────────────────────────────────────────

def test_3_put_brand_generic_when_live_brand_empty(monkeypatch):
    monkeypatch.setenv("COUPANG_BRAND_GENERIC", "1")
    live = dict(json.loads(json.dumps(LIVE)), brand="")
    up, calls = _up_with(monkeypatch, product=live)
    plan = up.live_fix_plan(up.get_product("16397045086"), name="", search_tags=None, brand="")
    assert plan["body"]["brand"] == "GENERIC"
    assert {"field": "브랜드", "before": "(비어 있음)", "after": "GENERIC"} in plan["changes"]
    # 원본에 브랜드가 있으면 손대지 않는다 · 플래그가 꺼져 있으면 예전 정본("")
    assert "브랜드" not in [c["field"] for c in up.live_fix_plan(dict(live, brand="ACME"), brand="")["changes"]]
    monkeypatch.setenv("COUPANG_BRAND_GENERIC", "0")
    assert up.live_fix_plan(live, brand="")["changes"] == []


def test_3_route_put_payload_has_generic(monkeypatch):
    monkeypatch.setenv("COUPANG_BRAND_GENERIC", "1")
    import src.seller_console.views as V
    _, calls = _up_with(monkeypatch, product=dict(json.loads(json.dumps(LIVE)), brand=""))
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    iid = _item("m8-put")
    d = _client("m8-put").post(f"/seller/collect/{iid}/live-fix", json={"market": "coupang:gogane"}).get_json()
    assert d["sent"] is True
    put = next(data for m, p, data in calls if m == "PUT")
    assert put["brand"] == "GENERIC"


def test_4_market_rejection_is_200_ok_false_with_raw_body(monkeypatch):
    import src.seller_console.views as V
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    raw = '{"code":"ERROR","message":"brandId 입력이 필요합니다. 브랜드가 없는 상품은 brand 필드에 GENERIC을 입력해 주세요."}'

    def api(self, method, path, data=None):
        self.last_sign = {"status": 400 if method == "PUT" else 200}
        if method == "PUT":
            return {"error": "쿠팡 거부 — stage=PUT … http_status=400", "error_body": raw}
        return {"code": "SUCCESS", "data": dict(json.loads(json.dumps(LIVE)), brand="ACME")}
    monkeypatch.setattr(CU, "_api_request", api)
    monkeypatch.setattr(V, "_coupang_up_for", lambda acct: CU(access_key="a", secret_key="b", vendor_id="A01381223"))
    iid = _item("m8-400")
    r = _client("m8-400").post(f"/seller/collect/{iid}/live-fix", json={"market": "coupang:gogane"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is False and d["market_status"] == 400 and "GENERIC" in d["body"]


def test_4_no_market_answer_is_502(monkeypatch):
    import src.seller_console.views as V
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)

    def api(self, method, path, data=None):
        if method == "PUT":
            self.last_sign = {"status": None}
            return {"error": "쿠팡 릴레이 실패 — RelayError"}
        self.last_sign = {"status": 200}
        return {"code": "SUCCESS", "data": dict(json.loads(json.dumps(LIVE)), brand="ACME")}
    monkeypatch.setattr(CU, "_api_request", api)
    monkeypatch.setattr(V, "_coupang_up_for", lambda acct: CU(access_key="a", secret_key="b", vendor_id="A01381223"))
    iid = _item("m8-502")
    r = _client("m8-502").post(f"/seller/collect/{iid}/live-fix", json={"market": "coupang:gogane"})
    assert r.status_code == 502 and r.get_json()["market_status"] is None


# ── 5. 쿠팡 상품명 끝 수식어 ─────────────────────────────────────────────────────────────────────

def test_5_pleats_name_drops_dangling_modifier():
    from src.uploaders.coupang_title import build_name
    t = AE9["title_ko"]
    r = build_name({"title_ko": t, "title": t})
    assert r["name"] == "플리츠 미니멀 여성 여름 세트"                              # 예전: 「… 여름 세트 디자인」
    assert any("짧아요" in w for w in r["warnings"])                                # 20자 하한은 경고로 정직하게


def test_5_cut_at_word_boundary_then_drop_modifier():
    from src.uploaders.coupang_title import _fit, _drop_dangling
    s = "가" * 40 + " 여름 세트 " + "나" * 40 + " 디자인 " + "다" * 20
    out = _fit(s)
    assert len(out) <= 100 and not out.endswith("디자인") and out.endswith("나" * 40)
    assert _drop_dangling("여름 세트 디자인 감각이") == "여름 세트"
    assert _drop_dangling("디자인") == "디자인"                                       # 한 낱말만 남으면 그대로
    mods = json.loads(Path("src/uploaders/coupang_name_modifiers.json").read_text(encoding="utf-8"))["modifiers"]
    assert {"디자인", "감각", "스타일"} <= set(mods)
