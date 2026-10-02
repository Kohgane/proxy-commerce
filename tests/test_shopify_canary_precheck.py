"""Shopify 캐너리 사전 점검(2026-09-28 — 수행방패 → catdyy-p0 1회 전에).

캐너리 전 코드를 읽어 찾은 것:
  ① 영문 제목 판정이 **한글만** 봤다 — 수행방패 원문은 중국어라 `title_en`(번역 실패 시 원문)이 통과,
     **중국어 제목이 US 스토어로** 갔을 것이다(F42d와 같은 결함). → 한·중·일 글자 전체로.
  ② 사전검증은 「닿는가」만 봤다 — 「통과」 뒤 등록에서 제목·판매가로 멈췄다(두 화면이 다른 말). → 사전검증이 먼저.
  ③ 실패하면 HTTP 사유가 화면까지 안 왔다 — 캐너리의 근거는 응답 원문이다. → `details`로 싣는다.
"""
from __future__ import annotations

import pytest

from src.seller_console import upload_dispatcher as U

SHIELD_ZH = "随行盾(SPORTLINK)适用于苹果手表充电支架applewatch7/9底座S8无线iwatch新款Ultra2手表架Airpods耳机架"


def _draft(**kw):
    d = {"title": SHIELD_ZH, "title_en": SHIELD_ZH, "title_original": SHIELD_ZH, "price": "29.90",
         "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"], "source_url": "https://detail.tmall.com/item.htm?id=617129397971"}
    d.update(kw)
    return d


@pytest.mark.parametrize("title", [SHIELD_ZH, "腕時計スタンド 充電", "애플워치 충전 거치대", "Apple Watch 充电支架"])
def test_cjk_titles_are_not_english(title):
    assert U.shopify_title({"title_en": title, "title": title}) == ""


def test_english_title_is_used_and_order_kept():
    assert U.shopify_title({"title_en": "Apple Watch Charging Stand", "title": SHIELD_ZH}) == "Apple Watch Charging Stand"
    assert U.shopify_title({"title_en": SHIELD_ZH, "title": "Charging Stand for Apple Watch"}) == "Charging Stand for Apple Watch"


def test_upload_holds_a_chinese_title(monkeypatch):
    d = U.UploadDispatcher()
    monkeypatch.setattr(d, "sell_price_in", lambda *a, **k: (19.99, ""))
    r = d._upload_shopify(_draft())
    assert r.success is False and r.error_code == "title_not_english" and "중국어" in r.message


def test_prevalidate_says_it_first(monkeypatch):
    d = U.UploadDispatcher()
    monkeypatch.setenv("SHOPIFY_SHOP", "catdyy-p0.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "x")
    called = []
    monkeypatch.setattr(U, "market_reach", lambda m: called.append(m) or {"ok": True, "ms": 5, "detail": "ok"})
    # 이미지 HEAD 검사(실네트워크)는 이 계약 밖이다 — 로컬 경로 이미지로 잰다(R2: 이미지 0장은 사전검증 「보류」).
    res = d._prevalidate_market(_draft(images=["/seller/static/icon-512.png"]), "shopify")
    assert res.ok is False and res.error_code == "title_not_english" and not called   # 두드리기 전에 멈춘다

    monkeypatch.setattr(d, "sell_price_in", lambda *a, **k: (None, "환율 없음"))
    res = d._prevalidate_market(_draft(title_en="Apple Watch Charging Stand", images=["/seller/static/icon-512.png"]), "shopify")
    assert res.ok is False and res.error_code == "price_unresolved" and "환율 없음" in res.message

    monkeypatch.setattr(d, "sell_price_in", lambda *a, **k: (19.99, ""))
    res = d._prevalidate_market(_draft(title_en="Apple Watch Charging Stand", images=["/seller/static/icon-512.png"]), "shopify")
    assert res.ok is True and called == ["shopify"]


def test_failure_carries_the_raw_reason(monkeypatch):
    from src.markets.adapters import shopify as S
    from src.markets.adapters.base import ListingResult

    class _A:
        def validate_listing(self, p):
            return ListingResult(ok=True, market="shopify", message="ok", raw={})

        def upload_product(self, p):
            return ListingResult(ok=False, market="shopify", message="Shopify 업로드 실패 (HTTP 422): 이미지",
                                 raw={"status": "api_error", "http_status": 422,
                                      "reason": "images: Image URL is invalid"})

    monkeypatch.setattr(S, "ShopifyAdapter", _A)
    d = U.UploadDispatcher()
    monkeypatch.setattr(d, "sell_price_in", lambda *a, **k: (19.99, ""))
    r = d._upload_shopify(_draft(title_en="Apple Watch Charging Stand"))
    assert r.success is False and r.details == ["HTTP 422", "images: Image URL is invalid"]


def test_adapter_internal_error_names_the_kind(monkeypatch):
    from src.markets.adapters.shopify import ShopifyAdapter
    from src.markets.adapters.base import ListingPayload
    a = ShopifyAdapter.__new__(ShopifyAdapter)
    monkeypatch.setattr(ShopifyAdapter, "validate_listing",
                        lambda self, p: __import__("src.markets.adapters.base", fromlist=["x"]).ListingResult(ok=True, market="shopify", message="", raw={}))

    def boom(self):
        raise KeyError("currency")
    monkeypatch.setattr(ShopifyAdapter, "_shop_profile", boom)
    r = a.upload_product(ListingPayload(title="T", description="", price=1.0, currency="USD", sku="", qty=0, options={}))
    assert r.ok is False and r.raw["status"] == "internal_error" and r.raw["error"].startswith("KeyError")


# ④ 채울 칸이 없었다 — 멈춤 안내는 「영문 상품명을 채우라」인데 드로어에 그 칸이 없었고,
#    등록은 수집 때 들어온 `title_en`(중국어 원문)을 먼저 썼다. 오너가 할 수 있는 일이 없었다.
def test_drawer_has_english_title_field_and_it_wins():
    from pathlib import Path
    t = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert 'id="editTitleEn"' in t and "영문 상품명" in t and "Shopify 등 해외 마켓용" in t
    assert "title_en: _ten || _EXTRA.title_en || title, title_en_input: _ten" in t
    assert "!_KGP_CJK.test(v)" in t          # 중국어 원문을 「영문」 칸에 채워 보이지 않는다


def test_save_stores_and_clears_the_english_title(monkeypatch):
    import json
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "u-shopify-en"
    iid = S.append(source="extension", seller_id=seller, url="https://detail.tmall.com/item.htm?id=617129397971",
                   title=SHIELD_ZH, price="29.90", currency="CNY",
                   extra={"title_en": SHIELD_ZH, "title": SHIELD_ZH})
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    r = c.post(f"/seller/collect/preview/{iid}/save", json={"title": "수행방패 애플워치 거치대",
                                                             "title_en_input": "Apple Watch Charging Stand"})
    assert r.get_json()["ok"], r.get_json()
    ex = json.loads(S.get(iid, seller_id=seller)["extra_json"])
    assert ex["title_en"] == "Apple Watch Charging Stand" and ex["title_en_manual"] is True
    assert U.shopify_title({**ex, "title": ex.get("title")}) == "Apple Watch Charging Stand"
    c.post(f"/seller/collect/preview/{iid}/save", json={"title": "수행방패 애플워치 거치대", "title_en_input": ""})
    ex = json.loads(S.get(iid, seller_id=seller)["extra_json"])
    assert "title_en" not in ex and "title_en_manual" not in ex
    # 칸을 안 보낸 저장(옛 화면)은 수집값을 건드리지 않는다.
    S.update(iid, seller_id=seller, extra_json=json.dumps({**ex, "title_en": SHIELD_ZH}, ensure_ascii=False))
    c.post(f"/seller/collect/preview/{iid}/save", json={"title": "수행방패"})
    assert json.loads(S.get(iid, seller_id=seller)["extra_json"])["title_en"] == SHIELD_ZH
