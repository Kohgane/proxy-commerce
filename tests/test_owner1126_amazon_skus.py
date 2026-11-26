"""오너 11-26 오후 ① — 아마존 옵션별 가격(자식 ASIN). 계약.

상품 화면엔 고른 옵션 가격만 있다 → 옵션 조합 → 자식 ASIN 표(`dimensionValuesDisplayData`, 값 순서는 `dimensions`)를 읽고
자식 화면마다 가격을 읽는다(간격·상한·실패 사유). 값 있는 조합만 SKU · 못 읽은 조합은 사유째 · 카드는 「가격 없는 n개 빼고 등록」 한 번.
"""
from __future__ import annotations

import json

import pytest

PAGE = ('"dimensions" : ["color_name","size_name"], "variationValues" : {"color_name":["Black","Green"],"size_name":["28L","40L"]}, "x": 1, '
        '"dimensionValuesDisplayData" : {"B0AAAAAAA1": ["Black", "28L"], "B0AAAAAAA2": ["Black", "40L"], "B0AAAAAAA3": ["Green", "28L"], '
        '"B0AAAAAAA4": ["Green", "40L"]}, "currentAsin" : "B0AAAAAAA2"')
CHILD = {"B0AAAAAAA1": '<div id="corePrice_feature_div"><span class="a-offscreen">KRW89,000</span></div><script>{"priceAmount":89000.5}</script>',
         "B0AAAAAAA2": '<div id="corePrice_feature_div"><span class="a-offscreen">KRW107,003</span></div><script>{"priceAmount":107002.62}</script>',
         "B0AAAAAAA3": '<div>Currently unavailable.</div>',
         "B0AAAAAAA4": None}


def _fetch(url):
    import re
    return CHILD[re.search(r"/dp/([A-Z0-9]{10})", url).group(1)]


def test_variants_and_child_prices_never_invent():
    from src.collectors import amazon_pdp as A
    v = A.variants(PAGE)
    assert v["dims"] == ["color_name", "size_name"] and v["current"] == "B0AAAAAAA2" and len(v["values_by_asin"]) == 4
    slept = []
    r = A.child_skus(v, _fetch, gap=1.5, sleep=slept.append)
    assert [(k["spec"], k["price"], k["currency"]) for k in r["skus"]] == [(["Black", "28L"], "89000.5", "KRW"), (["Black", "40L"], "107002.62", "KRW")]
    why = {tuple(m["spec"]): m["why"] for m in r["missing"]}
    assert why[("Green", "28L")] == "현재 구매 불가(가격 없음)" and why[("Green", "40L")].startswith("화면을 못 읽음")
    assert slept == [1.5, 1.5, 1.5] and r["read"] == 4                                  # 간격(첫 장 뒤부터)


def test_cap_is_reported_not_silently_dropped():
    from src.collectors import amazon_pdp as A
    v = {"values_by_asin": {f"B0CAP0000{i}": [f"c{i}"] for i in range(5)}}
    r = A.child_skus(v, lambda u: CHILD["B0AAAAAAA1"], gap=0, max_children=3, sleep=lambda s: None)
    assert len(r["skus"]) == 3 and r["capped"] == 2 and all("상한" in m["why"] for m in r["missing"])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


def _row(**ex):
    from src.seller_console import collect_history_store as S
    from src.collectors import amazon_pdp as A
    e = {"title_ko": "tomtoc 백팩", "images": ["https://m.media-amazon.com/images/I/81a._AC_SL1500_.jpg"], "price": "107002.62", "currency": "KRW",
         "options": [{"name": "색상", "values": ["Black", "Green"]}, {"name": "사이즈", "values": ["28L", "40L"]}],
         "amazon_variants": A.variants(PAGE), "sku_fill": {"state": "pending"}}
    e.update(ex)
    return S.append(source="share", url="https://www.amazon.com/dp/B0AAAAAAA2", title="tomtoc", price="107002.62", currency="KRW",
                    image="", seller_id="default", extra=e)


def test_fill_saves_priced_skus_and_reasons(client):
    from src.seller_console import collect_history_store as S
    from src.services import amazon_refetch as AR
    iid = _row()
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-code="sku_filling"' in h and "옵션별 가격을 읽는 중이에요(조합 4개)" in h
    out = AR.fill_skus(iid, {"default"}, fetch_html=_fetch, gap=0, sleep=lambda s: None)
    assert out["ok"] and out["priced"] == 2 and out["missing"] == 2
    ex = json.loads(S.get(iid, seller_id="default")["extra_json"])
    assert len(ex["skus"]) == 2 and ex["sku_fill"]["state"] == "done" and ex["field_sources"]["sku"] == "amazon_child"
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-code="sku_partial"' in h and "가격 없는 2개 빼고 등록" in h and "현재 구매 불가" in h
    d = client.post(f"/seller/collect/{iid}/drop-unpriced").get_json()
    assert d["ok"] and d["kept"] == 2 and d["dropped"] == 2 and d["dropped_values"] == ["색상: Green"]
    ex = json.loads(S.get(iid, seller_id="default")["extra_json"])
    assert ex["options"][0]["values"] == ["Black"] and ex["options"][1]["values"] == ["28L", "40L"] and ex["sku_missing_ack"]
    assert 'data-code="sku_partial"' not in client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    S.delete([iid], seller_id="default")


def test_fill_never_overwrites_seller_edits(client):
    from src.services import amazon_refetch as AR
    iid = _row(manual_fields={"sku": "2026-11-26T00:00:00+00:00"})
    out = AR.fill_skus(iid, {"default"}, fetch_html=_fetch, gap=0, sleep=lambda s: None)
    assert out["ok"] is False and "직접 고친" in out["error"]


def test_all_missing_says_refetch(client):
    from src.services import amazon_refetch as AR
    iid = _row()
    AR.fill_skus(iid, {"default"}, fetch_html=lambda u: None, gap=0, sleep=lambda s: None)
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-code="sku_none"' in h and "모두 가격을 못 읽었어요" in h and 'data-role="m5-drop-unpriced"' not in h
    assert client.post(f"/seller/collect/{iid}/drop-unpriced").status_code == 400


def test_collect_core_kicks_background_fill(monkeypatch):
    from src.api import extension_api as E
    from src.collectors.universal_scraper import ScrapedProduct
    from src.utils import bg_job
    jobs = []
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (jobs.append(name), (True, {}))[1])
    from src.collectors import amazon_pdp as A
    sp = ScrapedProduct(source_url="https://www.amazon.com/dp/B0AAAAAAA2", domain="amazon.com", title="tomtoc", description="",
                        images=["https://m.media-amazon.com/images/I/81a._AC_SL1500_.jpg"], price=None, currency="KRW")
    sp.raw_meta["amazon_pdp"] = {"image_source": "colorImages", "options": [{"name": "색상", "values": ["Black"]}], "variants": A.variants(PAGE)}
    monkeypatch.setattr(E, "_dispatcher_collect", lambda: (lambda url: sp))
    r = E.collect_one_url("https://www.amazon.com/dp/B0AAAAAAA2", seller_id="default", source="share")
    assert r["ok"] and jobs == [f"amazon-skus:{r['item_id']}"]
