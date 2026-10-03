"""X(오너 2026-10-04 00:42~00:57 캐너리 — 피샹리 1인용 소파 의자) — 우주대행 쿠팡 실패 2 · 고코스모스 보류 1.

X0 마켓 연동 › 쿠팡 = 계정별 카드(고가네 A01381223 · 우주대행 A01504840) · 계정 키로 출고지·반품지 불러오기 ·
   계정 스코프 저장(`coupang@woojoo`) → 등록은 DB 우선 → env 폴백 · 사전검증 문장에 계정명 · 계정 분리
X1 카테고리 메타 실패 = 원문(HTTP·본문)을 메시지·로그·기록에 · 계정별 비교 화면
X2 「원문 남음」 보류 = **나갈 글자**로 판정(가게 줄 원문 오판 제거) · 번역 보류는 자동 번역 먼저 · 「번역하고 다시 검증」
"""
from __future__ import annotations

import json

import pytest

GOGANE_DOM, GOGANE_OV, WOOJOO_DOM, WOOJOO_OV = "22796911", "25479338", "23612851", "26600001"


@pytest.fixture
def env(monkeypatch):
    import os
    for k in list(os.environ):
        if k.startswith("COUPANG_"):
            monkeypatch.delenv(k, raising=False)
    for k, v in {
        "COUPANG_ACCESS_KEY": "base-ak", "COUPANG_SECRET_KEY": "base-sk", "COUPANG_VENDOR_ID": "A01381223",
        "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": GOGANE_DOM, "COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE": GOGANE_OV,
        "COUPANG_GOGANE_OUTBOUND_SHIPPING_PLACE_CODE": GOGANE_DOM,
        "COUPANG_GOGANE_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE": GOGANE_OV,
        "COUPANG_GOGANE_VENDOR_USER_ID": "shanks8",
        "COUPANG_WOOJOO_ACCESS_KEY": "w-ak", "COUPANG_WOOJOO_SECRET_KEY": "w-sk", "COUPANG_WOOJOO_VENDOR_ID": "A01504840",
        "COUPANG_WOOJOO_OUTBOUND_SHIPPING_PLACE_CODE": WOOJOO_DOM,
        "COUPANG_DELIVERY_METHOD": "AGENT_BUY",
    }.items():
        monkeypatch.setenv(k, v)
    return monkeypatch


def _woojoo_uploader(seller="owner-x"):
    from src.seller_console import market_credentials as mc
    from src.seller_console.market_cred_view import coupang_account
    from src.channel_sync.coupang_uploader import make_uploader
    with mc.seller_market_env(seller, ["coupang:woojoo"]), coupang_account("woojoo"):
        return make_uploader()[0]


# ── X0 ─────────────────────────────────────────────────────────────────────────

def test_woojoo_outbound_hold_names_the_account_and_never_shows_gogane_ids(env):
    up = _woojoo_uploader()
    code, hold = up.outbound_for_delivery()
    assert code == "" and "우주대행 「구매대행 출고지 (해외)」가 비어 있습니다" in hold
    assert f"우주대행 국내 출고지 {WOOJOO_DOM}" in hold and "우주대행 카드" in hold
    assert GOGANE_DOM not in hold and GOGANE_OV not in hold                       # 계정 분리


def test_saved_oversea_profile_clears_the_hold_db_first(env):
    from src.seller_console import market_credentials as mc
    seller = "owner-x-save"
    mc.save_account_profile(seller, "woojoo", {"COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE": WOOJOO_OV,
                                               "COUPANG_ACCESS_KEY": "ignored"})
    assert mc.account_profile(seller, "woojoo") == {"COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE": WOOJOO_OV}
    assert mc.credential_env(seller, "coupang:woojoo") == {"COUPANG_WOOJOO_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE": WOOJOO_OV}
    up = _woojoo_uploader(seller)
    assert up.outbound_for_delivery() == (WOOJOO_OV, "")                         # 사유 ① 사라짐
    env.setenv("COUPANG_WOOJOO_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE", "99999999")
    assert _woojoo_uploader(seller).outbound_for_delivery()[0] == WOOJOO_OV      # DB 우선 → env 폴백
    with pytest.raises(ValueError):
        mc.save_account_profile(seller, "woojoo", {"COUPANG_SECRET_KEY": "x"})   # 키는 저장 안 함


def test_lookup_uses_the_account_keys(env, monkeypatch):
    from src.uploaders.coupang_uploader import CoupangUploader
    from src.seller_console.coupang_shipping_lookup import fetch
    seen = []

    def api(self, method, path, data=None):
        seen.append((self.access_key, self.vendor_id, path))
        if "outbound" in path:
            return {"data": {"content": [{"outboundShippingPlaceCode": int(WOOJOO_OV), "addressType": "OVERSEA",
                                          "shippingPlaceName": "우주대행 해외"},
                                         {"outboundShippingPlaceCode": int(WOOJOO_DOM), "addressType": "DOMESTIC",
                                          "shippingPlaceName": "우주대행 국내"}]}}
        return {"data": [{"returnCenterCode": "1000999", "shippingPlaceName": "우주대행 반품"}]}
    monkeypatch.setattr(CoupangUploader, "_api_request", api)
    out = fetch("woojoo")
    assert out["ok"] and out["vendor_id"] == "A01504840"
    assert {s[0] for s in seen} == {"w-ak"} and "A01504840" in seen[0][2] + seen[1][2]
    slots = {e["slot"]: e["values"] for e in out["outbound_places"]["entries"]}
    assert slots["COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE"]["COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE"] == WOOJOO_OV


def _admin(monkeypatch):
    from src.order_webhook import app
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner-x-route"; s["user_role"] = "admin"; s["email"] = "owner@example.com"
    return c


def test_connect_page_shows_two_account_cards_and_new_wording(env, monkeypatch):
    c = _admin(monkeypatch)
    h = c.get("/seller/markets/connect").get_data(as_text=True)
    assert h.count('data-role="coupang-account-card"') == 2
    assert 'data-account="gogane"' in h and 'data-account="woojoo"' in h and "A01504840" in h
    assert "COUPANG_WOOJOO_ACCESS_KEY/_SECRET_KEY" in h and "w-ak" not in h and "w-sk" not in h
    assert "쿠팡 판매자 계정마다 1개" in h and "판매자당 1개" not in h
    assert "쿠팡에서 출고지·반품지 불러오기 (우주대행)" in h


def test_account_routes_lookup_and_save(env, monkeypatch):
    import src.seller_console.coupang_shipping_lookup as L
    c = _admin(monkeypatch)
    monkeypatch.setattr(L, "fetch", lambda acct="": {"ok": True, "account": acct, "vendor_id": "A01504840",
                                                     "return_centers": {"entries": []}, "outbound_places": {"entries": []}})
    r = c.post("/seller/markets/connect/coupang/woojoo/lookup", json={})
    assert r.status_code == 200 and r.get_json()["account"] == "woojoo"
    assert c.post("/seller/markets/connect/coupang/nobody/lookup", json={}).status_code == 404
    r = c.post("/seller/markets/connect/coupang/woojoo/profile",
               json={"values": {"COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE": WOOJOO_OV}})
    assert r.status_code == 200 and r.get_json()["saved"]["COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE"] == WOOJOO_OV
    h = c.get("/seller/markets/connect").get_data(as_text=True)
    assert WOOJOO_OV in h and "저장값" in h


# ── X1 ─────────────────────────────────────────────────────────────────────────

def test_meta_failure_carries_the_raw_coupang_response(env, monkeypatch):
    from src.uploaders.coupang_uploader import CoupangUploader
    from src.db import image_translate_queue_pg as Q
    raw = 'HTTP 403: {"code":"ERROR","message":"권한이 없습니다(vendorId 불일치)"}'
    monkeypatch.setattr(CoupangUploader, "_api_request",
                        lambda self, m, p, data=None: {"error": raw} if "meta" in p.lower() or "category" in p.lower() else {})
    up = CoupangUploader(access_key="w-ak", secret_key="w-sk", vendor_id="A01504840", account="woojoo")
    assert up.get_category_meta("77723") == {} and up.meta_error("77723") == raw
    rows = Q.state_get("coupang:meta_probe")["rows"]
    assert rows[0]["account"] == "woojoo" and rows[0]["raw"] == raw and "w-ak" not in json.dumps(rows)
    from src.uploaders.coupang_options import plan_for
    plan = plan_for([], {"title": "소파"}, meta_ok=False)
    hold = next(h for h in plan["holds"] if "카테고리 메타를 읽지 못했습니다" in h)
    # precheck가 붙이는 꼬리(계정·카테고리·원문)
    monkeypatch.setattr(CoupangUploader, "predict_category", lambda self, n: "77723")
    out = up.precheck({"title": "소파", "sell_price_krw": 30000, "price": 30000, "images": ["https://x/a.jpg"]})
    tailed = [h for h in out["holds"] if h.startswith(hold)]
    assert tailed and "우주대행 · 카테고리 77723 · 쿠팡 응답: HTTP 403" in tailed[0]


def test_meta_compare_page_lists_both_accounts(env, monkeypatch):
    from src.uploaders.coupang_uploader import CoupangUploader
    from src.order_webhook import app

    def api(self, m, p, data=None):
        if self.account == "gogane":
            return {"data": {"attributes": [{"attributeTypeName": "색상"}], "noticeCategories": []}}
        return {"error": "HTTP 401: Invalid signature"}
    monkeypatch.setattr(CoupangUploader, "_api_request", api)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner-x"; s["user_role"] = "admin"; s["email"] = "owner@example.com"
    h = c.get("/admin/diagnostics/coupang-meta?category=77723").get_data(as_text=True)
    assert 'data-account="gogane"' in h and "메타 OK" in h and "속성 1개" in h
    assert 'data-account="woojoo"' in h and "메타 실패" in h and "Invalid signature" in h
    assert "w-ak" not in h and "base-ak" not in h


# ── X2 ─────────────────────────────────────────────────────────────────────────

_SOFA = {"title": "피샹리 1인용 소파 의자", "title_ko": "피샹리 1인용 소파 의자", "price": "1083.00", "currency": "CNY",
         "images": ["https://img.alicdn.com/a.jpg"], "sell_price_krw": 260000,
         "description": "菲尚丽家旗舰店\n5.0\n好评率98%\n物流好评率98%\n客服满意度93%", "description_ko": "",
         "keywords": ["피샹리", "소파", "의자"],
         "options": [{"name": "颜色分类", "name_ko": "색상", "values": ["德芙绒米白色座包+猫抓皮黑色底框"],
                      "values_ko": ["더브 플란넬 아이보리 방석 + 블랙 프레임"]}],
         "skus": [{"spec": ["德芙绒米白色座包+猫抓皮黑色底框"], "price": "1083.00"}]}


def test_shop_banner_original_no_longer_holds_smartstore():
    """캐너리 보류의 실제 원인: 사전검증만 **원문 상세**(가게 줄)를 봤다 — 등록은 그 줄을 뺀다."""
    from src.seller_console.upload_dispatcher import UploadDispatcher, outbound_foreign_fields
    assert outbound_foreign_fields(_SOFA) == [("상세", "菲尚丽家旗舰店")]                  # 예전 판정 재현
    holds = UploadDispatcher.readiness_holds(dict(_SOFA), "smartstore")
    assert not [h for h in holds if h["short"].startswith("원문(외국어) 남음")]


def _translate_ok(monkeypatch, ok=True):
    from src.seller_console.ai import translator as T

    def opts(self, options):
        vals = options[0]["values"]
        return {"provider": "papago", "options": [{"values": vals, "values_ko": (["블랙 프레임 소파"] * len(vals)) if ok else vals}]}
    monkeypatch.setattr(T.AITranslator, "translate_options", opts)
    monkeypatch.setattr(T.AITranslator, "translate_product", lambda self, p: {"title_ko": "", "provider": "none"})


def _open_smartstore(monkeypatch):
    """스마트스토어 게이트(토큰 실측·키)를 통과시켜 **준비 판정**까지 가게 한다."""
    from src.seller_console import smartstore_routing as SR
    monkeypatch.setattr(SR, "_issue", lambda st: {"state": "ok", "raw": "토큰 발급 OK", "count": 10, "count_raw": ""})
    SR.reset_cache()
    monkeypatch.setenv("NAVER_CLIENT_ID", "x")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "y")


def _item(seller):
    from src.seller_console import collect_history_store as S
    ex = json.loads(json.dumps(_SOFA))
    ex["options"][0]["values"] = ["朦胧月光款"]
    ex["options"][0]["values_ko"] = [""]
    ex["skus"] = [{"spec": ["朦胧月光款"], "price": "1083.00"}]
    return S.append(source="extension", url="https://item.taobao.com/item.htm?id=851803804374", seller_id=seller,
                    title="피샹리 1인용 소파 의자", price="1083.00", currency="CNY", extra=ex), ex


def test_translation_hold_is_auto_translated_before_holding(monkeypatch):
    from src.order_webhook import app
    seller = "owner-x2-ok"
    iid, ex = _item(seller)
    _open_smartstore(monkeypatch)
    _translate_ok(monkeypatch, ok=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    d = c.post("/seller/collect/prevalidate", json={"product": dict(ex, sell_price_krw=260000), "markets": ["smartstore"],
                                                    "item_id": iid}).get_json()
    assert d["auto_translate"]["status"] in ("done", "queued")
    r = d["results"][0]
    assert "옵션 값" not in (r["message"] or "") and "translate" not in r["fixes"]


def test_hold_stays_only_when_every_translator_fails(monkeypatch):
    from src.order_webhook import app
    seller = "owner-x2-fail"
    iid, ex = _item(seller)
    _open_smartstore(monkeypatch)
    _translate_ok(monkeypatch, ok=False)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    d = c.post("/seller/collect/prevalidate", json={"product": dict(ex, sell_price_krw=260000), "markets": ["smartstore"],
                                                    "item_id": iid}).get_json()
    assert d["auto_translate"]["status"] == "failed"
    r = d["results"][0]
    assert r["hold"] and "translate" in r["fixes"]
    t = c.post(f"/seller/collect/{iid}/translate-now", json={}).get_json()
    assert t["ok"] is False and t["status"] == "failed"


def test_m5_has_translate_and_recheck_button():
    from pathlib import Path
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert 'data-role="m5-translate-recheck"' in m5 and "/translate-now" in m5 and "refresh_from_store" in m5
