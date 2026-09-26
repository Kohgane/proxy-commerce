"""F51 — 쿠팡 **SKU별 다중 등록**(오너 결정 2026-09-26: 연다).

입력은 오너 실물: 수행방패 617129397971(颜色分类×10 · 재고 13/19/20/8/18/18/16/50/18/20 · 29.9/34.9 CNY)
— `tests/fixtures/realpages/tmall_617129397971_ice_min.html`(F49-T 2부-b).

| # | 계약 |
|---|---|
| 1 | SKU마다 item — 옵션명 颜色分类 → 용어집 → 메타 「색상」 · 원가 = 그 SKU 가격 · 재고 = quantity · 이미지 = 그 값 |
| 1' | 재고 0 SKU는 **빼고 사유를 적는다** |
| 2 | F48-c 「값이 N개」 보류는 **SKU가 있고 재고 있는 SKU 전부에 판매가가 있을 때만** 풀린다 — 아니면 문구 그대로 |
| 3 | 판매가는 SKU 원가로 **각각**(`_landed_krw` → `calc_sell_price` 하나) · 속성 3개 제한·색상 값 용어집 규칙은 SKU마다 |
| 3' | 색상 값이 용어집에 없으면 **보류 + 그 값 목록**(F48-b 규칙 — 짐작해 번역하지 않는다) |
| 4 | 같은 옵션 값이 두 SKU면 보류(쿠팡은 같은 옵션을 두 번 받지 않는다) |
| 5 | 쿠팡만 — 다른 마켓 경로는 SKU를 보지 않는다 |
"""
from __future__ import annotations

import json

import pytest

from src.uploaders import coupang_options as O
from tests.test_f49t2_tmall_ice_sku import F_617, res_of

pytestmark = pytest.mark.coupang_precheck

META = {
    "attributes": [
        {"attributeTypeName": "색상", "required": "MANDATORY", "dataType": "STRING", "exposed": "EXPOSED",
         "groupNumber": "NONE"},
        {"attributeTypeName": "수량", "required": "MANDATORY", "dataType": "NUMBER", "basicUnit": "개",
         "usableUnits": ["개"], "exposed": "EXPOSED", "groupNumber": "NONE"},
    ],
    "noticeCategories": [], "requiredDocumentNames": [],
}

# ★ 테스트 전용 **가정** 용어집 — 오너 정본이 아니다. 실제 용어집(D3)엔 黑色 하나뿐이라, 실값으로 돌리면
#   10개 전부 「용어집에 없음」 보류다(그 계약은 따로 잰다: test_unmapped_values_are_held_with_the_list).
FAKE_KO = {
    "三合一充电支架（白色）": "3-in-1 충전 거치대 화이트", "三合一充电支架（黑色）": "3-in-1 충전 거치대 블랙",
    "三合一充电支架（粉色）": "3-in-1 충전 거치대 핑크", "三合一充电支架（蓝色）": "3-in-1 충전 거치대 블루",
    "三合一充电支架（红色）": "3-in-1 충전 거치대 레드",
    "【三合一充电支架】带理线器（黑色）": "3-in-1 거치대+선정리 블랙", "【三合一充电支架】带理线器（白色）": "3-in-1 거치대+선정리 화이트",
    "【三合一充电支架】带理线器（蓝色）": "3-in-1 거치대+선정리 블루", "【三合一充电支架】带理线器（粉色）": "3-in-1 거치대+선정리 핑크",
    "【三合一充电支架】带理线器（红色）": "3-in-1 거치대+선정리 레드",
}


def _skus(price_fn=lambda cost: int(cost * 200)):
    """실물 → 확장이 보내는 SKU 모양(+ 판매가를 넣을지 말지는 호출부)."""
    res = res_of(F_617)
    vals = {v["vid"]: v for v in res["skuBase"]["props"][0]["values"]}
    info = res["skuCore"]["sku2info"]
    out = []
    for s in res["skuBase"]["skus"]:
        v = vals[s["propPath"].split(":")[1]]
        cost = int(info[s["skuId"]]["price"]["priceMoney"]) / 100
        k = {"spec": [v["name"]], "sku_id": s["skuId"], "price": f"{cost:.2f}", "currency": "CNY",
             "stock": info[s["skuId"]]["quantity"], "image": v["image"]}
        if price_fn:
            k["sell_price_krw"] = price_fn(cost)
        out.append(k)
    return out


def _product(skus):
    res = res_of(F_617)
    return {"title": res["item"]["title"], "price": 29.9, "currency": "CNY", "sku": "617129397971",
            "images": res["item"]["images"], "origin": "중국",
            "options": [{"name": "颜色分类", "values": [v["name"] for v in res["skuBase"]["props"][0]["values"]]}],
            "skus": skus}


@pytest.fixture
def ko(monkeypatch):
    monkeypatch.setattr(O, "color_ko", lambda v: FAKE_KO.get(v, ""))


# ── 1·3 SKU마다 item ──────────────────────────────────────────────────────────

def test_ten_skus_become_ten_items_with_their_own_price_stock_and_image(ko):
    plan = O.plan_for(META["attributes"], _product(_skus()))
    assert plan["multi"] is True and plan["holds"] == [], plan["holds"]
    items = plan["items"]
    assert len(items) == 10
    by = {it["sku_id"]: it for it in items}
    assert by["4852747022539"]["stock"] == 13 and by["4852747022539"]["sell_price_krw"] == int(34.9 * 200)
    assert by["4355552953968"]["stock"] == 50 and by["4355552953968"]["sell_price_krw"] == int(29.9 * 200)
    a = {x["attributeTypeName"]: x["attributeValueName"] for x in by["4355552953967"]["attributes"]}
    assert a == {"색상": "3-in-1 충전 거치대 화이트", "수량": "1개"}           # 颜色分类 → 색상(이름 용어집)
    assert by["4355552953967"]["image"].endswith("O1CN01miTzm827ieHRySwJf_!!2200774957831.jpg")


def test_zero_stock_is_left_out_with_a_reason(ko):
    skus = _skus()
    skus[0]["stock"] = 0                                    # 4355552953967(白色)
    plan = O.plan_for(META["attributes"], _product(skus))
    assert len(plan["items"]) == 9 and "4355552953967" not in {i["sku_id"] for i in plan["items"]}
    assert any("재고 0" in n and "三合一充电支架（白色）" in n for n in plan["notes"])


# ── 2 보류 해제 조건 ───────────────────────────────────────────────────────────

def test_without_sku_prices_the_old_hold_stays_verbatim():
    p = _product(_skus(price_fn=None))
    p["options"] = [{"name": "색상", "values": p["options"][0]["values"]}]   # F48-c 원 모양(메타 이름)
    plan = O.plan_for(META["attributes"], p)
    assert plan["multi"] is False
    assert any("「색상」 값이 10개입니다" in h and "SKU별 가격" in h for h in plan["holds"])


def test_one_sku_without_price_keeps_it_single():
    skus = _skus()
    skus[3].pop("sell_price_krw")
    plan = O.plan_for(META["attributes"], _product(skus))
    assert plan["multi"] is False and "판매가가 없는 SKU 1개" in plan["sku_why"]


# ── 3' 용어집 밖 색상 값 ───────────────────────────────────────────────────────

def test_unmapped_values_are_held_with_the_list():
    """실제 용어집(黑色만)으로 돌린다 — 10개 값이 전부 복합어라 **하나도 안 맞는다**. 짐작 번역 금지."""
    plan = O.plan_for(META["attributes"], _product(_skus()))
    assert plan["multi"] is True
    [h] = [h for h in plan["holds"] if h.startswith("색상 값")]
    assert h.startswith("색상 값 10개가 용어집에 없습니다") and "三合一充电支架（白色）" in h
    # 미매핑 SKU끼리 「같은 옵션」이라고 하지 않는다(공통 속성 수량만 남은 것 — 캡처에서 찾은 거짓 보류).
    assert not [x for x in plan["holds"] if "옵션 값이 같습니다" in x], plan["holds"]
    assert len(plan["holds"]) == 1


def test_unknown_option_name_is_held():
    p = _product(_skus())
    p["options"] = [{"name": "尺码", "values": p["options"][0]["values"]}]
    plan = O.plan_for(META["attributes"], p)
    assert any("옵션 「尺码」이 이 카테고리 메타에 없어 SKU별로 나눌 수 없습니다" in h for h in plan["holds"])


# ── 4 같은 값 두 번 ────────────────────────────────────────────────────────────

def test_two_skus_mapping_to_the_same_value_are_held(monkeypatch):
    monkeypatch.setattr(O, "color_ko", lambda v: "화이트" if "白色" in v else (FAKE_KO.get(v, "")))
    plan = O.plan_for(META["attributes"], _product(_skus()))
    assert any("옵션 값이 같습니다" in h for h in plan["holds"])


def test_a_typed_axis_value_does_not_flatten_every_sku(ko):
    p = _product(_skus())
    p["attributes"] = [{"attributeTypeName": "색상", "attributeValueName": "블랙"}]
    plan = O.plan_for(META["attributes"], p)
    assert plan["holds"] == [] and len({i["attributes"][0]["attributeValueName"] for i in plan["items"]}) == 10


def test_a_pick_narrows_to_that_sku(ko):
    p = O.apply_choices(_product(_skus()), None, {"颜色分类": "三合一充电支架（黑色）"})
    plan = O.plan_for(META["attributes"], p)
    assert [i["sku_id"] for i in plan["items"]] == ["4355552953968"]


# ── 3 SKU별 판매가(식 하나) ─────────────────────────────────────────────────────

def test_sku_prices_come_from_each_sku_cost(monkeypatch):
    from src.channel_sync.coupang_uploader import with_sku_prices
    from src.seller_console.upload_dispatcher import UploadDispatcher
    seen = []

    def fake(pd, market=""):
        seen.append((pd["price_original"], pd["currency"], market))
        return float(pd["price_original"]) * 250, ""
    monkeypatch.setattr(UploadDispatcher, "_landed_krw", staticmethod(fake))
    out = with_sku_prices({"currency": "CNY", "price": 29.9, "skus": _skus(price_fn=None)})
    assert {s for s in seen} == {(29.9, "CNY", "coupang"), (34.9, "CNY", "coupang")}
    assert {k["sell_price_krw"] for k in out["skus"]} == {int(round(29.9 * 250)), int(round(34.9 * 250))}


def test_a_sku_that_cannot_be_priced_says_why(monkeypatch):
    from src.channel_sync.coupang_uploader import with_sku_prices
    from src.seller_console.upload_dispatcher import UploadDispatcher
    monkeypatch.setattr(UploadDispatcher, "_landed_krw", staticmethod(lambda pd, m="": (0.0, "coupang 판매수수료율이 없습니다")))
    out = with_sku_prices({"skus": _skus(price_fn=None)})
    assert all("sell_price_krw" not in k and "수수료" in k["price_why"] for k in out["skus"])


# ── 등록 페이로드(실경로: 브리지 → prepare → precheck → payload) ────────────────

SHIP = {
    "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A0001",
    "COUPANG_VENDOR_USER_ID": "wing", "COUPANG_RETURN_CENTER_CODE": "1000",
    "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": "22796911",
    "COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE": "25099966",
    "COUPANG_RETURN_ZIP_CODE": "06236", "COUPANG_RETURN_ADDRESS": "서울", "COUPANG_RETURN_CHARGE_NAME": "CS",
    "COUPANG_COMPANY_CONTACT_NUMBER": "02-1", "COUPANG_DELIVERY_COMPANY_CODE": "CJGLS", "COUPANG_IMAGE_SCREEN": "0",
}


@pytest.fixture
def wired(monkeypatch, ko):
    for k, v in SHIP.items():
        monkeypatch.setenv(k, v)
    from src.uploaders.coupang_uploader import CoupangUploader
    from src.seller_console.upload_dispatcher import UploadDispatcher
    posts = []

    def _api(self, method, path, data=None):
        if "categorization/predict" in path:
            return {"data": {"predictedCategoryId": "63955"}}
        if "category-related-metas" in path:
            return {"data": META}
        if "shipping-place/outbound" in path:
            return {"data": [{"outboundShippingPlaceCode": "25099966", "addressType": "OVERSEA"}]}
        if method == "POST" and path.rstrip("/").endswith("seller-products"):
            posts.append(data)
            return {"code": "SUCCESS", "data": 1}
        return {"code": "SUCCESS", "data": None}

    monkeypatch.setattr(CoupangUploader, "_api_request", _api)
    monkeypatch.setattr(UploadDispatcher, "_landed_krw",
                        staticmethod(lambda pd, m="": (float(pd["price_original"]) * 250, "")))
    monkeypatch.setattr("src.seller_console.market_cred_view.coupang_api_state",
                        lambda: {"missing": [], "account": ""})
    monkeypatch.setattr("src.seller_console.market_cred_view.coupang_shipping_state",
                        lambda acct: {"missing": [], "source": ""})
    monkeypatch.setattr("src.seller_console.market_cred_view.resolve_upload_account", lambda: "")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: __import__("contextlib").nullcontext())
    return posts


def test_registration_sends_one_item_per_sku(wired):
    from src.channel_sync import coupang_uploader as bridge
    skus = _skus(price_fn=None)
    skus[0]["stock"] = 0
    bridge.upload({**_product(skus), "sell_price_krw": 9000})
    [payload] = wired
    items = payload["items"]
    assert len(items) == 9
    by = {it["externalVendorSku"]: it for it in items}
    it = by["4852747022539"]                                 # 34.9 CNY · 재고 13
    assert it["salePrice"] == 8800 and it["originalPrice"] == 10100      # ceil100(34.9×250=8725)=8800 · ×1.15
    assert it["maximumBuyCount"] == 13
    assert it["itemName"] == "3-in-1 거치대+선정리 블랙"                    # 옵션 값만(수량 「1개」는 이름에 안 넣음)
    assert it["images"][0]["imageType"] == "REPRESENTATION" and "O1CN01VH5g2D27ieHYAj48U" in it["images"][0]["vendorPath"]
    assert {i["salePrice"] for i in items} == {7500, 8800}                # 29.9×250=7475→7500
    assert len({json.dumps(i["attributes"], ensure_ascii=False) for i in items}) == 9
    assert all(len(i["attributes"]) <= O.MAX_ATTRIBUTES for i in items)


def test_prevalidate_says_it_will_register_per_sku(wired):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-f51-pre"
    r = c.post("/seller/collect/prevalidate", json={"product": _product(_skus(price_fn=None)),
                                                   "markets": ["coupang"]}).get_json()["results"][0]
    assert r["ok"] is True, r
    assert "SKU별 등록 10개" in r["hint"]
    assert wired == []


def test_the_editor_sends_skus():
    html = open("src/seller_console/templates/collect_preview.html", encoding="utf-8").read()
    body = html.split("function buildProductData", 1)[1].split("\n}\n", 1)[0]
    assert "skus: Array.isArray(_EXTRA.skus) ? _EXTRA.skus : []" in body


def test_other_markets_ignore_skus():
    """F51은 쿠팡만 — 다른 업로더 경로는 `skus`를 읽지 않는다(구조가 다르다 — 별도 트랙)."""
    import pathlib
    for f in ("src/channel_sync/elevenst_uploader.py", "src/channel_sync/smartstore_uploader.py"):
        p = pathlib.Path(f)
        if p.exists():
            assert "skus" not in p.read_text(encoding="utf-8")
