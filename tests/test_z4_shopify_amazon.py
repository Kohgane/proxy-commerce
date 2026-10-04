"""Z4(오너 2026-10-04) — 범용 Shopify 수집기 + 아마존 링크 일괄 입력(404 = 존재하지 않는 상품).

이 컨테이너는 sewtites.com·amazon.com에 못 나간다(송신 정책) → Shopify `/products/<handle>.json` **모양**(Shopify 공식
문서의 product 객체 키)과 HTTP 상태를 대역으로 쓴다. 상품 값은 지어낸 표본이다(실측은 배포 뒤 운영에서).
"""
from __future__ import annotations

import pytest

SEWTITES_LIKE = {"product": {
    "id": 1, "title": "Magnum (sample)", "vendor": "SewTites", "body_html": "<p>Reusable silicone <b>pins</b></p>",
    "options": [{"name": "Color", "values": ["Black", "Red"]}, {"name": "Pack", "values": ["10", "20"]}],
    "variants": [{"option1": "Black", "option2": "10", "price": "24.99", "sku": "MAG-B-10", "available": True},
                 {"option1": "Black", "option2": "20", "price": "39.99", "sku": "MAG-B-20", "available": True},
                 {"option1": "Red", "option2": "10", "price": "24.99", "sku": "MAG-R-10", "available": False},
                 {"option1": "Red", "option2": "20", "price": "39.99", "sku": "MAG-R-20", "available": True}],
    "images": [{"src": "https://cdn.shopify.com/a.jpg"}, {"src": "https://cdn.shopify.com/b.jpg"}]}}


def test_shopify_json_becomes_a_full_draft(monkeypatch):
    import src.collectors.adapters.shopify_generic as G
    seen = []
    monkeypatch.setattr(G, "_fetch_shopify_json", lambda u: (seen.append(u), SEWTITES_LIKE)[1])
    from src.seller_console.views import _collect_real_draft
    d = _collect_real_draft("https://sewtites.com/products/magnum?variant=1", translate=False)
    assert seen == ["https://sewtites.com/products/magnum.json"]
    assert d["source"] == "shopify-json" and d["title"] == "Magnum (sample)" and d["brand"] == "SewTites"
    assert d["images"] == ["https://cdn.shopify.com/a.jpg", "https://cdn.shopify.com/b.jpg"]
    assert d["options"] == [{"name": "Color", "values": ["Black", "Red"]}, {"name": "Pack", "values": ["10", "20"]}]
    assert len(d["skus"]) == 4 and d["skus"][1] == {"spec": ["Black", "20"], "price": "39.99", "sku": "MAG-B-20", "available": True}
    assert d["price"] == "24.99"                                              # 가장 싼 조합
    assert d["currency"] == "" and d["price_status"] == "needs_check"        # 통화를 USD로 짐작하지 않는다
    assert any("통화" in w for w in d["warnings"])


def test_not_shopify_falls_back_and_unreadable_is_unsupported(monkeypatch):
    import src.collectors.adapters.shopify_generic as G
    monkeypatch.setattr(G, "_fetch_shopify_json", lambda u: None)
    with pytest.raises(G.NotShopify):
        G.ShopifyGenericAdapter().fetch("https://barryking.com/products/x")
    from src.collectors import dispatcher as D
    from src.collectors.universal_scraper import ScrapedProduct
    monkeypatch.setattr(D._dispatcher.fallback, "fetch", lambda u: ScrapedProduct(source_url=u, domain="x", title="", description=""))
    assert D.collect("https://csosborne.com/products/knife").extraction_method == "unsupported"   # 「미지원 사이트」


def test_default_title_placeholder_option_is_dropped():
    from src.collectors.adapters.shopify_generic import parse_product
    p = parse_product({"title": "One", "images": [{"src": "x"}], "options": [{"name": "Title", "values": ["Default Title"]}],
                       "variants": [{"option1": "Default Title", "price": "10.00"}]}, "https://crimsonhides.com/products/one")
    assert p.options == [] and p.raw_meta["skus"][0]["spec"] == []


class _R:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


def test_amazon_check_states():
    from src.collectors.amazon_check import check
    u = "https://www.amazon.com/dp/B0ABCDEFGH"
    assert check(u, get=lambda *a: _R(404))["state"] == "not_found"
    assert check(u, get=lambda *a: _R(200, "<title>Amazon.com: Pins</title>"))["state"] == "exists"
    wall = check(u, get=lambda *a: _R(200, "<form action='/errors/validateCaptcha'>"))
    assert wall["state"] == "unknown" and "로봇 확인" in wall["why"]               # 벽은 「없음」이 아니다
    assert check(u, get=lambda *a: _R(503))["state"] == "unknown"


def test_bulk_ten_amazon_links_counts_and_skips_404(monkeypatch):
    from src.order_webhook import app
    from src.collectors import amazon_check as A
    import src.collectors.share_collect as SC
    dead = {f"B0DEAD000{i}" for i in range(4)}
    monkeypatch.setattr(A, "check", lambda url, get=None: {
        "state": "not_found" if A.asin(url) in dead else ("unknown" if A.asin(url).endswith("5") else "exists"),
        "status": 404 if A.asin(url) in dead else 200, "asin": A.asin(url), "why": ""})
    called = []
    monkeypatch.setattr(SC, "collect_input", lambda block, **kw: (called.append(block), {"ok": False, "error": "봇 차단", "url": block})[1])
    urls = [f"https://www.amazon.com/dp/B0DEAD000{i}" for i in range(4)] + \
           [f"https://www.amazon.com/dp/B0LIVE000{i}" for i in range(6)]
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner-z4"
    d = c.post("/seller/collect/bulk", json={"urls": "\n".join(urls)}).get_json()
    assert d["total"] == 10 and d["amazon"] == {"exists": 5, "not_found": 4, "unknown": 1}
    nf = [r for r in d["results"] if r.get("not_found")]
    assert len(nf) == 4 and all("존재하지 않는 상품" in r["error"] for r in nf)
    assert len(called) == 6                                                    # 404는 수집기를 안 부른다


def test_bulk_ui_shows_amazon_counts():
    from pathlib import Path
    h = Path("src/seller_console/templates/manual_collect.html").read_text(encoding="utf-8")
    assert 'data-role="amazon-check"' in h and "존재하지 않는 상품 ${data.amazon.not_found}" in h


def test_taobao_mtop_probe_page_numbers_only(monkeypatch):
    """Z3 실측 화면 — 숫자·ret만(쿠키·토큰 값 0). 네트워크는 대역."""
    from src.collectors import taobao_mtop as T
    monkeypatch.setattr(T, "probe", lambda q: {"input": q, "item_id": "733241700286", "how": "주소의 id=",
                                               "log": ["1차: HTTP 200 · ret=['FAIL_SYS_TOKEN_EMPTY::令牌为空'] · 토큰 쿠키 없음",
                                                       "2차: HTTP 200 · ret=['SUCCESS::调用成功'] · 토큰 쿠키 있음"],
                                               "detail": {"title_len": 18, "title": "格斯潘懒人沙发", "price": "798",
                                                          "gallery": 5, "skus": 4, "axes": 2, "values": 5}, "desc_images": 12})
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-mtop?q=https://item.taobao.com/item.htm?id=733241700286").get_data(as_text=True)
    assert 'data-role="mtop-numbers"' in h and "갤러리 5" in h and "SKU 4" in h and "상세 이미지 12" in h
    assert T.summarize({"data": {"item": {"title": "ab", "images": [1, 2]}, "skuBase": {"skus": [1], "props": [{"values": [1, 2]}]}}}) == \
        {"title_len": 2, "title": "ab", "price": "", "gallery": 2, "skus": 1, "axes": 1, "values": 2}
