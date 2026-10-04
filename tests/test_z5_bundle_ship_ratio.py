"""Z5(오너 2026-10-04, 교체) — 우주대행 묶음 기본 체크 · 한 마켓 보류가 다른 마켓을 막지 않음 · 배송비 비율 보류 + 「그래도 등록」."""
from __future__ import annotations

import json

import pytest

SOFA = {"title_src": "格斯潘懒人沙发单人", "title": "격스판 빈백 소파 1인용", "title_ko": "격스판 빈백 소파 1인용",
        "price": "780", "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/b.jpg"]}
LAMP = {"title_src": "【BLACKHOLES】黑洞小夜灯", "title": "블랙홀 미니 무드등", "title_ko": "블랙홀 미니 무드등",
        "price": "69.9", "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/b.jpg"]}


@pytest.fixture(autouse=True)
def _fx(monkeypatch):
    from src.seller_console import data_aggregator as D
    monkeypatch.setattr(D, "get_fx_rates", lambda: {"CNY": 188.4, "USD": 1370.5})
    monkeypatch.delenv("SHIPPING_RATIO_HOLD_PCT", raising=False)


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
    box = {"title": "접이식 수납함 40x30x20cm", "price": "50", "currency": "CNY"}
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
    base = [{"code": m, "label": m, "connected": True, "checked": m == "coupang"} for m in ("coupang", "smartstore", "elevenst")]
    by = {m["code"]: m for m in V._with_coupang_accounts(base, {})}
    assert by["coupang:woojoo"]["checked"] and by["smartstore:gocosmos"]["checked"]          # 우주대행 묶음 둘 다
    assert not by["coupang:gogane"]["checked"] and not by["smartstore:chezgoga"]["checked"]   # 고가네 묶음은 손으로
    monkeypatch.setenv("MARKET_DEFAULT_BUSINESS", "gogane")
    by = {m["code"]: m for m in V._with_coupang_accounts(base, {})}
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
