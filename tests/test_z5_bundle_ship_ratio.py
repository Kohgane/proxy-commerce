"""Z5(오너 2026-10-04, 교체) — 우주대행 묶음 기본 체크 · 한 마켓 보류가 다른 마켓을 막지 않음 · 배송비 비율 보류 + 「그래도 등록」."""
from __future__ import annotations

import json

import pytest

SOFA = {"url": "https://item.taobao.com/item.htm?id=733241700286", "title_src": "格斯潘懒人沙发单人", "title": "격스판 빈백 소파 1인용", "title_ko": "격스판 빈백 소파 1인용",
        "price": "780", "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/b.jpg"]}
LAMP = {"url": "https://detail.tmall.hk/item.htm?id=1", "title_src": "【BLACKHOLES】黑洞小夜灯", "title": "블랙홀 미니 무드등", "title_ko": "블랙홀 미니 무드등",
        "price": "69.9", "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/b.jpg"]}


@pytest.fixture(autouse=True)
def _fx(monkeypatch):
    from src.seller_console import data_aggregator as D
    monkeypatch.setattr(D, "get_fx_rates", lambda: {"CNY": 188.4, "USD": 1370.5})
    for k in ("SHIPPING_RATIO_HOLD_PCT", "SHIPPING_RATE_KRW_PER_KG_CN_DIRECT", "SHIPPING_RATE_KRW_PER_KG_CN_FORWARDER",
              "SHIPPING_RATE_KRW_PER_KG_US", "SHIPPING_VOL_DIVISOR_CN", "SHIPPING_VOL_DIVISOR_US"):
        monkeypatch.delenv(k, raising=False)
    # Z5 후속: 중국발 요율은 기본값이 없다(오너가 준다) — 계약은 시험값 18000으로 잰다.
    monkeypatch.setenv("SHIPPING_RATE_KRW_PER_KG_CN", "18000")


def test_sofa_is_held_by_shipping_ratio_and_lamp_passes():
    from src.seller_console.shipping_ratio import estimate, hold
    from src.seller_console.upload_dispatcher import UploadDispatcher
    s = estimate(SOFA)
    assert s["state"] == "ok" and s["ratio_pct"] > 35 and "소파 기본값" in s["basis"]
    h = [x for x in UploadDispatcher.readiness_holds(dict(SOFA), "coupang") if x["fix"] == "ship_ratio"]
    assert h and h[0]["short"].startswith("배송비 비율 초과 ") and "%" in h[0]["short"]
    lamp = estimate(LAMP)
    assert lamp["state"] == "unknown" and lamp["line"].startswith("부피 미확인")       # 못 잰 건 통과
    assert hold(dict(LAMP)) is None
    assert not [x for x in UploadDispatcher.readiness_holds(dict(LAMP), "coupang") if x["fix"] == "ship_ratio"]


def test_threshold_and_read_dimensions(monkeypatch):
    from src.seller_console.shipping_ratio import estimate, hold
    box = {"url": "https://item.taobao.com/item.htm?id=2", "title": "접이식 수납함 40x30x20cm", "price": "50", "currency": "CNY"}
    e = estimate(box)
    assert e["basis"] == "상품 글에서 읽은 치수" and e["chargeable_kg"] == 4.0
    monkeypatch.setenv("SHIPPING_RATIO_HOLD_PCT", "10000")
    assert hold(box) is None                                                   # 임계값 env


def test_size_table_is_remote_json(monkeypatch):
    from src.seller_console import shipping_ratio as S
    from src.db import image_translate_queue_pg as st
    st.reset_for_tests()
    S.save_rules({"size_defaults": [{"label": "무드등", "keywords": ["무드등"], "dims_cm": [10, 10, 10], "weight_kg": 0.3}]})
    try:
        assert "무드등 기본값" in S.estimate(LAMP)["basis"]
        with pytest.raises(ValueError):
            S.save_rules({"size_defaults": [{"label": "x"}]})
    finally:
        S.save_rules(None)


def _client(seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["email"] = seller, "cn-user@example.com"
    return c


def test_override_button_records_and_releases_hold(monkeypatch):
    for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID", "COUPANG_VENDOR_USER_ID",
              "COUPANG_RETURN_CENTER_CODE", "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE", "COUPANG_RETURN_ZIP_CODE",
              "COUPANG_RETURN_ADDRESS", "COUPANG_RETURN_CHARGE_NAME", "COUPANG_COMPANY_CONTACT_NUMBER"):
        monkeypatch.setenv(k, "x1")
    from src.seller_console import collect_history_store as S
    seller = "owner-z5-override"
    ex = dict(SOFA)
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=733241700286", seller_id=seller,
                   title=SOFA["title"], price="780", currency="CNY", extra=ex)
    c = _client(seller)
    d = c.post("/seller/collect/prevalidate", json={"product": dict(SOFA), "markets": ["coupang"], "item_id": iid}).get_json()
    r = d["results"][0]
    assert r["hold"] and "ship_ratio" in r["fixes"] and "배송비 비율 초과" in r["message"]
    o = c.post(f"/seller/collect/{iid}/ship-ratio-override").get_json()
    assert o["ok"] and o["override"]["by"] == "cn-user@example.com" and "추정 배송비" in o["override"]["line"]
    saved = json.loads(S.get(iid, seller_ids={seller})["extra_json"])["ship_ratio_override"]
    assert saved["ratio_pct"] > 35
    d = c.post("/seller/collect/prevalidate", json={"product": dict(SOFA), "markets": ["coupang"], "item_id": iid}).get_json()
    assert "ship_ratio" not in (d["results"][0].get("fixes") or [])            # 같은 화면 상품으로 다시 → 풀림


def test_m5_has_override_button_wiring():
    from pathlib import Path
    h = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert "indexOf('ship_ratio')" in h and 'data-role="m5-ship-override"' in h and "그래도 등록" in h


def test_default_bundle_is_woojoo(monkeypatch):
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    from src.seller_console import market_cred_view as MCV, smartstore_routing as SR
    monkeypatch.setattr(MCV, "coupang_account_choices", lambda: [
        {"code": "coupang:gogane", "account": "gogane", "label": "쿠팡 — 고가네", "ready": True, "missing": []},
        {"code": "coupang:woojoo", "account": "woojoo", "label": "쿠팡 — 우주대행", "ready": True, "missing": []}])
    monkeypatch.setattr(SR, "store_choices", lambda p=None: [
        {"code": "smartstore:chezgoga", "store": "chezgoga", "label": "스마트스토어 — 셰고가", "business": "gogane",
         "ready": True, "approved": True, "assigned": True, "note": "", "limit_text": "셰고가 850/1,000"},
        {"code": "smartstore:gocosmos", "store": "gocosmos", "label": "스마트스토어 — 고코스모스", "business": "woojoo",
         "ready": True, "approved": True, "assigned": False, "note": "", "limit_text": "고코스모스 881/1,000"}])
    # Z5 후속(2026-10-06): 기본 체크는 `market_pick.apply_checks`가 정한다(지난 등록 → 설정 → 묶음) — 묶음 판정만 여기서
    from src.seller_console import market_pick as MP
    from src.db import image_translate_queue_pg as st
    st.reset_for_tests()
    base = [{"code": m, "label": m, "connected": True, "checked": m == "coupang"} for m in ("coupang", "smartstore", "elevenst")]
    rows = V._with_coupang_accounts(base, {})
    MP.apply_checks(rows, "shared")
    by = {m["code"]: m for m in rows}
    assert by["coupang:woojoo"]["checked"] and by["smartstore:gocosmos"]["checked"]          # 우주대행 묶음 둘 다
    assert not by["coupang:gogane"]["checked"] and not by["smartstore:chezgoga"]["checked"]   # 고가네 묶음은 손으로
    monkeypatch.setenv("MARKET_DEFAULT_BUSINESS", "gogane")
    rows = V._with_coupang_accounts(base, {})
    MP.apply_checks(rows, "shared")
    by = {m["code"]: m for m in rows}
    assert by["coupang:gogane"]["checked"] and not by["coupang:woojoo"]["checked"]


def test_full_gocosmos_holds_only_its_line(monkeypatch):
    """고코스모스 1,000 → 그 줄만 「보류: 스토어 한도」, 쿠팡 우주대행은 그대로 등록(전부-아니면-전무 아님)."""
    from src.seller_console import smartstore_routing as SR
    from src.seller_console.upload_dispatcher import UploadDispatcher, UploadResult
    monkeypatch.setattr(SR, "limit_state", lambda st, fetch=None: {"count": 1000, "limit": 1000, "full": True,
                                                                  "text": "고코스모스 1,000/1,000"})
    monkeypatch.setattr(SR, "price_hold", lambda pd: "")
    import src.seller_console.upload_dispatcher as UD
    monkeypatch.setattr(UD, "smartstore_approved", lambda: True)
    sent = []
    orig = UploadDispatcher._dispatch_one

    def one(self, pd, market):
        if market == "coupang":
            sent.append(market)
            return UploadResult(market=market, success=True, message="등록됨 16400000001")
        return orig(self, pd, market)
    monkeypatch.setattr(UploadDispatcher, "_dispatch_one", one)
    res = UploadDispatcher().dispatch(dict(LAMP), ["coupang:woojoo", "smartstore:gocosmos"])
    by = {r.market: r for r in res.results}
    assert by["coupang:woojoo"].success and sent == ["coupang"]
    assert not by["smartstore:gocosmos"].success and "보류: 스토어 한도" in by["smartstore:gocosmos"].message
    assert res.succeeded == 1 and res.failed == 1



def test_rates_by_origin_and_route(monkeypatch):
    """Z5 후속(오너 10-04 20:30): 출발국·발주 경로별 요율 env — 중국발 기본값 없음(판정 생략) · 미국발 18,000 기본."""
    from src.seller_console import shipping_ratio as S
    monkeypatch.delenv("SHIPPING_RATE_KRW_PER_KG_CN", raising=False)
    e = S.estimate(dict(SOFA))
    assert e["state"] == "unknown" and e["line"].startswith("요율 미설정 — 비율 판정 생략") and S.hold(dict(SOFA)) is None
    monkeypatch.setenv("SHIPPING_RATE_KRW_PER_KG_CN_DIRECT", "6000")
    monkeypatch.setenv("SHIPPING_RATE_KRW_PER_KG_CN_FORWARDER", "9000")
    assert "발주 경로 미설정" in S.estimate(dict(SOFA))["line"]                      # 경로별만 있고 경로를 안 골랐다
    d = S.estimate(dict(SOFA, ship_route="direct"))
    f = S.estimate(dict(SOFA, ship_route="forwarder"))
    assert "중국 현지 직접 발송 6,000원/kg" in d["line"] and "배대지 경유 9,000원/kg" in f["line"]
    monkeypatch.setenv("SHIPPING_VOL_DIVISOR_CN_DIRECT", "5000")
    assert S.estimate(dict(SOFA, ship_route="direct"))["chargeable_kg"] == round(90 * 80 * 70 / 5000, 1)
    us = S.estimate({"url": "https://www.amazon.com/dp/B0X", "title": "box 40x30x20cm", "price": "20", "currency": "USD"})
    assert "미국발 18,000원/kg" in us["line"]
    assert S.estimate({"url": "https://zozo.jp/x", "title": "의자", "price": "2000", "currency": "JPY"})["line"].startswith("출발국 요율 없음")


def test_account_default_route_and_product_override(monkeypatch):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as CH, shipping_ratio as S
    from src.db import image_translate_queue_pg as st
    st.reset_for_tests()
    monkeypatch.delenv("SHIPPING_RATE_KRW_PER_KG_CN", raising=False)
    monkeypatch.setenv("SHIPPING_RATE_KRW_PER_KG_CN_FORWARDER", "9000")
    seller = "owner-z5-route"
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    assert "계정 기본값" in c.get("/seller/settings/ship-route").get_data(as_text=True)
    c.post("/seller/settings/ship-route", data={"route": "forwarder"})
    assert S.account_route(seller) == "forwarder"
    assert "배대지 경유 9,000원/kg" in S.estimate(dict(SOFA, seller_id=seller), seller)["line"]   # 계정 기본
    iid = CH.append(source="extension", url=SOFA["url"], seller_id=seller, title="빈백", price="780", currency="CNY", extra=dict(SOFA))
    assert c.post(f"/seller/collect/{iid}/ship-route", json={"route": "direct"}).get_json()["ok"]
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-ship-route"' in h and 'value="direct" selected' in h
    assert "요율 미설정" in h                                                          # 직접 발송 요율은 아직 없음
