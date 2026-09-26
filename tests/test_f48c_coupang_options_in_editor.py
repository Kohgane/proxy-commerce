"""F48-c — 사전검증이 멈춘 쿠팡 옵션을 **오너가 편집 화면에서 푼다.**

오너 화면 원문(2026-09-26):
  - 「필수 옵션: 적용모델」
  - 「「색상」 값이 13개입니다 — 여러 옵션 등록은 SKU별 가격이 필요합니다(지금은 한 값만 남겨 주세요)」
  - 「옵션 「옵션」은 이 카테고리 메타에 없어 옵션으로 보내지 않습니다(검색어로만)」

계약:
  ① 칸은 카테고리 메타의 MANDATORY 속성 그대로(dataType·usableUnits·그룹), 값은 **찾은 것만**(기본값 0)
  ② 오너가 넣은 값만 attributes로 간다 — 비우면 보류 유지
  ③ 옵션 값 13개 중 **목록에 있던 값 하나**를 고르면 단일 SKU로 통과(목록 밖 값은 무시)
  ④ 예전엔 입력한 속성이 브리지에서 **떨어졌다**(`to_collected`·`prepare_product`) — 이제 끝까지 간다
  ⑤ 사전검증 라우트로 실제로: 멈춤 → 칸 채움 + 하나 고름 → 통과
"""
from __future__ import annotations

import pytest

from src.uploaders import coupang_options as O

pytestmark = pytest.mark.coupang_precheck

COLORS = ["黑色", "白色", "红色", "蓝色", "绿色", "黄色", "粉色", "紫色", "灰色", "棕色", "橙色", "米色", "卡其色"]
META = {
    "attributes": [
        {"attributeTypeName": "적용모델", "required": "MANDATORY", "dataType": "STRING", "exposed": "EXPOSED",
         "groupNumber": "NONE"},
        {"attributeTypeName": "색상", "required": "MANDATORY", "dataType": "STRING", "exposed": "EXPOSED",
         "groupNumber": "NONE"},
        {"attributeTypeName": "수량", "required": "MANDATORY", "dataType": "NUMBER", "basicUnit": "개",
         "usableUnits": ["개"], "exposed": "EXPOSED", "groupNumber": "NONE"},
    ],
    "noticeCategories": [], "requiredDocumentNames": [],
}
PRODUCT = {"title": "수행방패 케이스", "price": 24000, "currency": "KRW", "sku": "617129397971",
           "images": ["https://img.alicdn.com/a.jpg"], "origin": "중국",
           "options": [{"name": "색상", "values": COLORS}, {"name": "옵션", "values": ["기본"]}]}


def test_the_screen_shows_the_three_holds_verbatim_before_anything_is_entered():
    plan = O.plan_attributes(META["attributes"], dict(PRODUCT))
    assert plan["holds"][0] == "필수 옵션: 적용모델"
    assert any("「색상」 값이 13개입니다" in h and "SKU별 가격" in h for h in plan["holds"])
    assert any("옵션 「옵션」은 이 카테고리 메타에 없어" in n for n in plan["notes"])


def test_the_form_lists_meta_fields_as_is_and_fills_only_found_values():
    f = O.option_form(META["attributes"], dict(PRODUCT))
    by = {x["name"]: x for x in f["fields"]}
    assert set(by) == {"적용모델", "색상", "수량"}
    assert by["적용모델"]["value"] == ""                          # 찾은 값 없음 → 빈칸(지어내지 않는다)
    assert by["색상"]["value"] == "" and "SKU별 가격" in by["색상"]["why"]
    assert by["수량"]["value"] == "1" and by["수량"]["usableUnits"] == ["개"] and by["수량"]["dataType"] == "NUMBER"
    assert f["choices"] == [{"name": "색상", "values": COLORS, "in_meta": True}]


def test_owner_values_and_one_pick_clear_the_holds():
    chosen = O.apply_choices(dict(PRODUCT),
                             [{"attributeTypeName": "적용모델", "attributeValueName": "iPhone 15"}],
                             {"색상": "黑色"})
    plan = O.plan_attributes(META["attributes"], chosen)
    assert plan["holds"] == []
    got = {a["attributeTypeName"]: a["attributeValueName"] for a in plan["attributes"]}
    assert got == {"적용모델": "iPhone 15", "색상": "블랙", "수량": "1개"}


def test_an_empty_owner_value_keeps_the_hold():
    chosen = O.apply_choices(dict(PRODUCT), [{"attributeTypeName": "적용모델", "attributeValueName": "  "}],
                             {"색상": "黑色"})
    assert O.plan_attributes(META["attributes"], chosen)["holds"] == ["필수 옵션: 적용모델"]


def test_a_pick_outside_the_list_is_ignored():
    chosen = O.apply_choices(dict(PRODUCT), None, {"색상": "파란색이라고 지어낸 값"})
    assert next(o for o in chosen["options"] if o["name"] == "색상")["values"] == COLORS


def test_an_unmapped_chinese_pick_can_be_overridden_by_a_typed_value():
    """고른 값이 용어집에 없는 한자면 보류 — 오너가 **색상 칸에 한국어를 넣으면** 그 값이 이긴다."""
    picked = O.apply_choices(dict(PRODUCT), [{"attributeTypeName": "적용모델", "attributeValueName": "X"}],
                             {"색상": "卡其色"})
    assert any("색상 미매핑: 卡其色" in h for h in O.plan_attributes(META["attributes"], picked)["holds"])
    typed = O.apply_choices(picked, [{"attributeTypeName": "색상", "attributeValueName": "카키"}])
    assert O.plan_attributes(META["attributes"], typed)["holds"] == []


def test_typed_attributes_survive_the_bridge_to_the_uploader():
    """④ 예전엔 `to_collected`·`prepare_product`에서 떨어져, 칸에 넣어도 사전검증·등록에 안 갔다."""
    from src.channel_sync._channel_bridge import to_collected
    from src.channel_sync.coupang_uploader import with_choices
    from src.uploaders.coupang_uploader import CoupangUploader
    pd = {**PRODUCT, "coupang_attributes": [{"attributeTypeName": "적용모델", "attributeValueName": "iPhone 15"}],
          "coupang_option_pick": {"색상": "黑色"}}
    prepared = CoupangUploader(access_key="a", secret_key="b", vendor_id="v").prepare_product(
        to_collected(with_choices(pd)))
    assert prepared["attributes"][0] == {"attributeTypeName": "적용모델", "attributeValueName": "iPhone 15"}
    assert next(o for o in prepared["options"] if o["name"] == "색상")["values"] == ["黑色"]


SHIP = {
    "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A0001",
    "COUPANG_VENDOR_USER_ID": "wing", "COUPANG_RETURN_CENTER_CODE": "1000",
    "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": "22796911",
    "COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE": "25099966",
    "COUPANG_RETURN_ZIP_CODE": "06236", "COUPANG_RETURN_ADDRESS": "서울", "COUPANG_RETURN_CHARGE_NAME": "CS",
    "COUPANG_COMPANY_CONTACT_NUMBER": "02-1", "COUPANG_DELIVERY_COMPANY_CODE": "CJGLS", "COUPANG_IMAGE_SCREEN": "0",
}


@pytest.fixture
def wired(monkeypatch):
    for k, v in SHIP.items():
        monkeypatch.setenv(k, v)
    from src.uploaders.coupang_uploader import CoupangUploader
    posts = []

    def _api(self, method, path, data=None):
        if "categorization/predict" in path:            # 예측도 POST다 — 등록과 가르려면 경로 먼저
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
    monkeypatch.setattr("src.seller_console.market_cred_view.coupang_api_state",
                        lambda: {"missing": [], "account": ""})
    monkeypatch.setattr("src.seller_console.market_cred_view.coupang_shipping_state",
                        lambda acct: {"missing": [], "source": ""})
    monkeypatch.setattr("src.seller_console.market_cred_view.resolve_upload_account", lambda: "")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: __import__("contextlib").nullcontext())
    return posts


def _client(seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def test_the_editor_block_route_returns_the_meta_fields(wired):
    d = _client("u-f48c-form").post("/seller/collect/coupang/options", json={"product": PRODUCT}).get_json()
    assert d["ok"] is True and d["category"] == "63955"
    assert [f["name"] for f in d["fields"]] == ["적용모델", "색상", "수량"]
    assert d["holds"][0] == "필수 옵션: 적용모델" and d["choices"][0]["name"] == "색상"


def test_prevalidate_goes_from_held_to_passed_once_the_owner_fills_the_block(wired):
    c = _client("u-f48c-pre")
    held = c.post("/seller/collect/prevalidate", json={"product": PRODUCT, "markets": ["coupang"]}).get_json()
    r = held["results"][0]
    assert r["ok"] is False and r["error_code"] == "coupang_hold" and "필수 옵션: 적용모델" in r["details"]
    filled = {**PRODUCT, "coupang_attributes": [{"attributeTypeName": "적용모델", "attributeValueName": "iPhone 15"}],
              "coupang_option_pick": {"색상": "黑色"}}
    ok = c.post("/seller/collect/prevalidate", json={"product": filled, "markets": ["coupang"]}).get_json()
    assert ok["results"][0]["ok"] is True, ok
    assert wired == []                                    # 사전검증은 전송 0회


def test_registration_sends_exactly_what_the_owner_chose(wired):
    from src.channel_sync import coupang_uploader as bridge
    filled = {**PRODUCT, "price": 24000, "sell_price_krw": 24000,
              "coupang_attributes": [{"attributeTypeName": "적용모델", "attributeValueName": "iPhone 15"}],
              "coupang_option_pick": {"색상": "黑色"}}
    bridge.upload(filled)
    [payload] = wired
    attrs = {a["attributeTypeName"]: a["attributeValueName"] for a in payload["items"][0]["attributes"]}
    assert attrs == {"적용모델": "iPhone 15", "색상": "블랙", "수량": "1개"}


def test_the_choices_are_saved_with_the_draft():
    from src.seller_console import collect_history_store as S
    iid = S.append(url="https://detail.tmall.com/item.htm?id=617129397971", title="t", price="24000",
                   currency="KRW", source="extension", seller_id="u-f48c-save", extra={"options": PRODUCT["options"]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = _client("u-f48c-save")
    r = c.post(f"/seller/collect/preview/{iid}/save", json={
        "title": "t", "coupang_attributes": [{"attributeTypeName": "적용모델", "attributeValueName": "iPhone 15"},
                                             {"attributeTypeName": "빈칸", "attributeValueName": ""}],
        "coupang_option_pick": {"색상": "黑色"}})
    assert r.get_json()["ok"]
    import json
    ex = json.loads(S.get(iid, seller_ids={"u-f48c-save"})["extra_json"])
    assert ex["coupang_attributes"] == [{"attributeTypeName": "적용모델", "attributeValueName": "iPhone 15"}]
    assert ex["coupang_option_pick"] == {"색상": "黑色"}


def test_the_pick_list_stays_after_a_pick_and_the_sent_values_are_shown(wired):
    """캡처에서 찾은 것 — 고른 뒤 목록이 사라져 다시 고를 수 없었다. 보낼 값(黑色→블랙)도 따로 보인다."""
    filled = {**PRODUCT, "coupang_attributes": [{"attributeTypeName": "적용모델", "attributeValueName": "iPhone 15"}],
              "coupang_option_pick": {"색상": "黑色"}}
    d = _client("u-f48c-stay").post("/seller/collect/coupang/options", json={"product": filled}).get_json()
    assert d["choices"] == [{"name": "색상", "values": COLORS, "in_meta": True}]
    assert {a["attributeTypeName"]: a["attributeValueName"] for a in d["attributes"]}["색상"] == "블랙"


def test_in_a_real_browser_only_typed_values_and_the_pick_go_out(wired):
    """JS를 **실행해서** 잰다: 찾은 값은 오너 값으로 굳지 않고, 친 값과 고른 값만 `buildProductData`에 실린다."""
    pw = pytest.importorskip("playwright.sync_api")
    import glob
    from src.seller_console import collect_history_store as S
    iid = S.append(url="https://detail.tmall.com/item.htm?id=617129397971", title="수행방패 케이스", price="24000",
                   currency="KRW", source="extension", seller_id="u-f48c-js",
                   extra={"options": PRODUCT["options"], "images": PRODUCT["images"]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = _client("u-f48c-js")
    html = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    data = c.post("/seller/collect/coupang/options", json={"product": PRODUCT}).get_json()
    seller_js = open("src/seller_console/static/seller.js", encoding="utf-8").read()
    html = html.replace('<script src="/seller/static/seller.js"></script>', "<script>" + seller_js + "</script>")
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    with pw.sync_playwright() as p:
        br = p.chromium.launch(**({"executable_path": hits[0]} if hits else {}))
        pg = br.new_page()
        # 페이지를 **실제 주소**에서 연다 — set_content(about:blank)면 상대 경로 fetch가 실패한다.
        pg.route("http://app.test/seller/collect/coupang/options", lambda r: r.fulfill(json=data))
        pg.route("http://app.test/seller/collect/preview/*",
                 lambda r: r.fulfill(body=html, content_type="text/html; charset=utf-8"))
        pg.route("http://app.test/**", lambda r: r.fulfill(body="", status=204)
                 if "/coupang/options" not in r.request.url and "/collect/preview/" not in r.request.url
                 else r.fallback())
        pg.goto(f"http://app.test/seller/collect/preview/{iid}")
        pg.evaluate("() => kgpEtab('options')")                  # 옵션 탭(블록이 사는 곳)을 연다
        pg.evaluate("(d) => kgpRenderCoupangOptions(d)", data)
        before = pg.evaluate("() => buildProductData().coupang_attributes")
        pg.fill('[data-cp-attr="적용모델"]', "iPhone 15")
        # 고르면 **바로 다시 확인**(블록을 다시 그린다) — 요소가 바뀌므로 click 후 새 요소를 기다린다.
        pg.click('[data-cp-pick="색상"][value="白色"]')
        pg.wait_for_selector('[data-cp-pick="색상"][value="白色"]:checked')
        out = pg.evaluate("() => ({a: buildProductData().coupang_attributes, p: buildProductData().coupang_option_pick})")
        br.close()
    assert before == []                                           # 찾은 값(수량 1)은 오너 값이 아니다
    assert out["a"] == [{"attributeTypeName": "적용모델", "attributeValueName": "iPhone 15"}]
    assert out["p"] == {"색상": "白色"}
