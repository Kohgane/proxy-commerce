"""F48 계약 — 쿠팡 등록 거부 2건(배송방법 · 구매옵션)을 **전송 전에** 잡는다.

## 오너 브리프 (2026-09-25 · 9/30 D-5)

| # | 무엇 |
|---|---|
| a | `deliveryMethod=AGENT_BUY`면 `outboundShippingPlaceCode`는 **해외 주소지만** — 국내 22796911을 보내 거부 |
| b | 카테고리 메타로 MANDATORY 누락 보류 · groupNumber 택1 · 메타 이름만 · NUMBER=값+단위 · 색상 용어집 |
| c | 오류 문장 `|` 분리 + `errorItems[].itemAttributes[].message`를 **그대로** 화면에 |
| d | 사전검증에 a·b — **등록을 눌러야 아는 건 늦다** |

오너 계약: **메타 목에서 누락/불일치/그룹 위반이 전송 0회로 잡힌다.**

⚠️ 정직 표기 — 오너가 붙여 넣었다는 **문서 원문이 이 세션에 도달하지 않았다**(포털은 이 환경에서 차단).
그래서 메타 목은 **브리프가 받아 적은 필드**(`MANDATORY`·`groupNumber`·`EXPOSED`·`dataType`·
`usableUnits`·`requiredDocumentNames`·`errorItems[].itemAttributes[].message`)와 **레포가 이미 실응답에서
읽고 있는 필드**(`attributeTypeName`·`required`·`exposed`·`basicUnit`)로만 만들었다.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.uploaders import coupang_options as O
from src.uploaders.coupang_uploader import CoupangUploader
from tests._ast_probe import calls_in

#: 깊은 판정(카테고리·메타·출고지)을 **실제로** 재는 계약 — conftest의 「안 쟀다」 기본값을 끈다.
pytestmark = pytest.mark.coupang_precheck

DOMESTIC = "22796911"       # 장말로 — 볼트: 국내배송용, AGENT_BUY로 쓰면 거부
OVERSEA = "25099966"        # ForAmazon — 볼트: AGENT_BUY 전용

SHIP_ENV = {
    "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A0001",
    "COUPANG_VENDOR_USER_ID": "wing", "COUPANG_RETURN_CENTER_CODE": "1000",
    "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": DOMESTIC, "COUPANG_RETURN_ZIP_CODE": "06236",
    "COUPANG_RETURN_ADDRESS": "서울", "COUPANG_RETURN_CHARGE_NAME": "CS",
    "COUPANG_COMPANY_CONTACT_NUMBER": "02-1", "COUPANG_DELIVERY_COMPANY_CODE": "CJGLS",
}


def _meta(attrs=None, docs=None):
    """카테고리 메타 `data` — 브리프가 적은 필드와 레포가 실응답에서 읽는 필드만."""
    return {
        "attributes": attrs if attrs is not None else [
            {"attributeTypeName": "수량", "dataType": "NUMBER", "basicUnit": "개",
             "usableUnits": ["개"], "required": "MANDATORY", "exposed": "EXPOSED",
             "groupNumber": "NONE"},
            {"attributeTypeName": "색상", "dataType": "STRING", "required": "MANDATORY",
             "exposed": "EXPOSED", "groupNumber": "NONE"},
            {"attributeTypeName": "gtin", "dataType": "STRING", "required": "MANDATORY",
             "exposed": "NONE", "groupNumber": "NONE"},
        ],
        "noticeCategories": [{"noticeCategoryName": "기타 재화", "noticeCategoryDetailNames": [
            {"noticeCategoryDetailName": "품명 및 모델명", "required": "MANDATORY"},
            {"noticeCategoryDetailName": "제조국(원산지)", "required": "MANDATORY"}]}],
        "requiredDocumentNames": docs if docs is not None else [],
    }


@pytest.fixture
def up(monkeypatch):
    for k, v in SHIP_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE", raising=False)
    monkeypatch.delenv("COUPANG_INVOICE_DOCUMENT_URL", raising=False)
    monkeypatch.setenv("COUPANG_IMAGE_SCREEN", "0")
    u = CoupangUploader()
    monkeypatch.setattr(u, "predict_category", lambda *a, **k: "1001")
    return u


def _no_post(up, meta, address_type="OVERSEA"):
    """메타·출고지 조회만 답하고 **POST가 나가면 실패**하는 목 — 「전송 0회」를 잰다."""
    posts = []

    def _api(method, path, data=None):
        if method == "POST":
            posts.append(data)
            return {"code": "SUCCESS", "data": 123}
        if "shipping-place/outbound" in path:
            # 물어본 코드를 그대로 돌려준다 — 조회는 **그 코드의** 주소 유형을 본다.
            asked = path.split("placeCodes=")[-1]
            return {"data": [{"outboundShippingPlaceCode": asked, "addressType": address_type}]}
        if "category-related-metas" in path:
            return {"data": meta}
        return {"code": "SUCCESS", "data": None}

    up._api_request = _api
    return posts


PRODUCT = {"sku": "617129397971", "title": "수행방패 휴대용 방패", "price": 24000,
           "images": ["https://img/1.jpg"], "brand": "", "origin": "중국",
           "options": [], "description_html": "<p>상세</p>"}


# ---------------------------------------------------------------------------
# a) 배송 — AGENT_BUY는 해외 출고지만
# ---------------------------------------------------------------------------

def test_agent_buy_never_falls_back_to_the_domestic_code(up):
    """★★★ **이번 거부의 모양** — 해외 칸이 비었는데 국내 코드로 떨어지면 쿠팡이 거부한다."""
    assert up.is_agent_buy()
    code, hold = up.outbound_for_delivery()
    assert code == "" and "해외 주소지만" in hold and DOMESTIC in hold


def test_a_missing_overseas_code_is_held_before_sending(up):
    posts = _no_post(up, _meta())
    res = up.upload_product({**PRODUCT, "options": [{"name": "색상", "values": ["블랙"]}]})
    assert res["success"] is False and res["held"] is True
    assert "해외 주소지만" in res["error"]
    assert posts == []                                                      # 전송 0회


def test_agent_buy_sends_the_overseas_code(up, monkeypatch):
    monkeypatch.setattr(up, "overseas_outbound_place_code", OVERSEA)
    posts = _no_post(up, _meta())
    res = up.upload_product({**PRODUCT, "options": [{"name": "색상", "values": ["블랙"]}]})
    assert res["success"] is True, res
    sent = posts[0]
    assert sent["deliveryMethod"] == "AGENT_BUY"
    assert sent["outboundShippingPlaceCode"] == int(OVERSEA)
    # 선례(andobil 16369251981 판매중)와 같은 세트 — 구매대행 표기 + PCC.
    item = sent["items"][0]
    assert item["overseasPurchased"] == "OVERSEAS_PURCHASED" and item["pccNeeded"] is True


def test_a_domestic_code_in_the_overseas_slot_is_caught(up, monkeypatch):
    """★★ 칸 이름만 믿지 않는다 — 조회해서 **정말 해외인가**를 본다."""
    monkeypatch.setattr(up, "overseas_outbound_place_code", DOMESTIC)
    posts = _no_post(up, _meta(), address_type="DOMESTIC")
    chk = up.precheck({**PRODUCT, "options": [{"name": "색상", "values": ["블랙"]}]})
    assert chk["ok"] is False and any("OVERSEA" in h and "DOMESTIC" in h for h in chk["holds"])
    assert posts == []


def test_an_unreadable_address_type_is_a_note_not_a_block(up, monkeypatch):
    """조회가 안 되면 **모른다**고 적는다 — 모르는 걸 막는 근거로 쓰지 않는다."""
    monkeypatch.setattr(up, "overseas_outbound_place_code", OVERSEA)
    _no_post(up, _meta(), address_type="")
    chk = up.precheck({**PRODUCT, "options": [{"name": "색상", "values": ["블랙"]}]})
    assert chk["ok"] is True and any("확인하지 못했습니다" in n for n in chk["notes"])


def test_sequencial_uses_the_domestic_code(up, monkeypatch):
    monkeypatch.setattr(up, "delivery_method", "SEQUENCIAL")
    assert up.outbound_for_delivery() == (DOMESTIC, "")


INVOICE = "인보이스영수증(해외구매대행 선택시)"


def test_a_required_invoice_without_url_is_held(up, monkeypatch):
    """★★ 오너: 인보이스 URL은 **오너 결정 사항** — 없으면 전송 전 보류 + 사유."""
    monkeypatch.setattr(up, "overseas_outbound_place_code", OVERSEA)
    posts = _no_post(up, _meta(docs=[{"templateName": INVOICE, "required": "MANDATORY"}]))
    res = up.upload_product({**PRODUCT, "options": [{"name": "색상", "values": ["블랙"]}]})
    assert res["held"] is True and INVOICE in res["error"] and "오너 결정" in res["error"]
    assert posts == []


def test_the_invoice_rides_on_document_path(up, monkeypatch):
    """★★★ F48-b — 오너 문서 정본: `requiredDocuments[templateName=…].documentPath`."""
    monkeypatch.setattr(up, "overseas_outbound_place_code", OVERSEA)
    monkeypatch.setattr(up, "invoice_document_url", "https://files/invoice.pdf")
    assert CoupangUploader.REQUIRED_DOC_PATH_KEY == "documentPath"
    docs, hold = up.required_documents_plan(_meta(docs=[INVOICE]))
    assert hold == "" and docs == [{"templateName": INVOICE, "documentPath": "https://files/invoice.pdf"}]


def test_no_invoice_hold_when_the_category_does_not_ask(up, monkeypatch):
    monkeypatch.setattr(up, "overseas_outbound_place_code", OVERSEA)
    assert up.required_documents_plan(_meta(docs=[])) == ([], "")


def test_load_places_split_by_address_type(monkeypatch):
    """★★ 「불러오기」 — OVERSEA만 구매대행 칸 후보, 국내는 국내 칸, 유형 모름은 **자동 배정 안 함**."""
    from src.seller_console import coupang_shipping_lookup as L

    class _U:
        access_key, secret_key, vendor_id = "a", "s", "A1"

        def _api_request(self, method, path, data=None):
            if "outbound" in path:
                return {"data": [
                    {"outboundShippingPlaceCode": OVERSEA, "shippingPlaceName": "ForAmazon",
                     "addressType": "OVERSEA"},
                    {"outboundShippingPlaceCode": DOMESTIC, "shippingPlaceName": "장말로",
                     "addressType": "DOMESTIC"},
                    {"outboundShippingPlaceCode": "999", "shippingPlaceName": "모름"}]}
            return {"data": []}

    monkeypatch.setattr(L, "_uploader", lambda acct: _U())
    monkeypatch.setattr("src.seller_console.market_cred_view.resolve_upload_account", lambda: "")
    got = L.fetch("")
    rows = {e["label"]: e for e in got["outbound_places"]["entries"]}
    assert rows["ForAmazon"]["values"] == {L.OVERSEAS_OUTBOUND_ENV: OVERSEA}
    assert rows["장말로"]["values"] == {L.DOMESTIC_OUTBOUND_ENV: DOMESTIC}
    assert rows["모름"]["values"] == {} and rows["모름"]["code_unassigned"] == "999"


# ---------------------------------------------------------------------------
# b) 구매옵션 — 메타가 정본, 모르면 올리지 않는다
# ---------------------------------------------------------------------------

def test_missing_mandatory_is_held_not_invented():
    """★★★ 옛 경로는 색상을 모르면 `블랙`을 지어 넣었다 — 이제 **보류**한다."""
    plan = O.plan_attributes(_meta()["attributes"], dict(PRODUCT))
    assert plan["holds"][0] == "필수 옵션: 색상"
    assert all(a["attributeValueName"] != "블랙" for a in plan["attributes"])


def test_gtin_is_never_an_option():
    """바코드는 `emptyBarcode`+사유로 따로 말한다 — 필수여도 옵션 칸의 일이 아니다(옛 정본 5,691건)."""
    plan = O.plan_attributes(_meta()["attributes"], {**PRODUCT, "options": [{"name": "색상", "values": ["블랙"]}]})
    assert not plan["holds"]
    assert all("gtin" not in a["attributeTypeName"] for a in plan["attributes"])


def test_number_attributes_carry_a_meta_unit():
    """★ `dataType=NUMBER` → 값 + usableUnits 단위(「1개」)."""
    plan = O.plan_attributes(_meta()["attributes"], {**PRODUCT, "options": [{"name": "색상", "values": ["블랙"]}]})
    qty = [a for a in plan["attributes"] if a["attributeTypeName"] == "수량"][0]
    assert qty["attributeValueName"] == "1개" and qty["exposed"] == "EXPOSED"


def test_a_unit_outside_usable_units_is_held():
    attrs = [{"attributeTypeName": "개당 중량", "dataType": "NUMBER", "basicUnit": "g",
              "usableUnits": ["g", "kg"], "required": "MANDATORY", "exposed": "EXPOSED"}]
    plan = O.plan_attributes(attrs, {**PRODUCT, "attributes": [
        {"attributeTypeName": "개당 중량", "attributeValueName": "3oz"}]})
    assert plan["holds"] and "허용 밖 단위" in plan["holds"][0]


def test_group_number_takes_exactly_one():
    """★★ groupNumber 택1 — 같은 그룹 필수 속성은 **하나만**, 채울 수 있는 것으로."""
    attrs = [{"attributeTypeName": "개당 용량", "dataType": "NUMBER", "basicUnit": "ml",
              "usableUnits": ["ml"], "required": "MANDATORY", "exposed": "EXPOSED", "groupNumber": "1"},
             {"attributeTypeName": "개당 중량", "dataType": "NUMBER", "basicUnit": "g",
              "usableUnits": ["g"], "required": "MANDATORY", "exposed": "EXPOSED", "groupNumber": "1"}]
    plan = O.plan_attributes(attrs, {**PRODUCT, "attributes": [
        {"attributeTypeName": "개당 중량", "attributeValueName": "250"}]})
    names = [a["attributeTypeName"] for a in plan["attributes"]]
    assert names == ["개당 중량"] and plan["attributes"][0]["attributeValueName"] == "250g"
    assert not plan["holds"]


def test_a_group_with_nothing_fillable_is_held_by_name():
    attrs = [{"attributeTypeName": "개당 용량", "required": "MANDATORY", "groupNumber": 1},
             {"attributeTypeName": "개당 중량", "required": "MANDATORY", "groupNumber": 1}]
    plan = O.plan_attributes(attrs, dict(PRODUCT))
    assert plan["holds"] == ["필수 옵션(택1): 개당 용량 또는 개당 중량"]


def test_taobao_option_names_not_in_meta_go_to_search_only():
    """★★ 자유옵션은 노출 제한 — 메타에 없는 옵션명은 **옵션으로 안 보내고** 검색어로만."""
    plan = O.plan_attributes(
        [{"attributeTypeName": "수량", "dataType": "NUMBER", "usableUnits": ["개"],
          "required": "MANDATORY", "exposed": "EXPOSED"}],
        {**PRODUCT, "options": [{"name": "颜色分类", "values": ["黑色", "白色"]}]})
    assert [a["attributeTypeName"] for a in plan["attributes"]] == ["수량"]
    assert plan["search_extra"] == ["黑色", "白色"] and not plan["holds"]


def test_a_chinese_colour_uses_the_d3_glossary():
    attrs = [{"attributeTypeName": "색상", "required": "MANDATORY", "exposed": "EXPOSED"}]
    ok = O.plan_attributes(attrs, {**PRODUCT, "options": [{"name": "색상", "values": ["黑色"]}]})
    assert ok["attributes"][0]["attributeValueName"] == "블랙" and not ok["holds"]
    bad = O.plan_attributes(attrs, {**PRODUCT, "options": [{"name": "색상", "values": ["白色"]}]})
    assert bad["holds"] and "색상 미매핑: 白色" in bad["holds"][0]


def test_the_colour_table_is_the_d3_glossary_not_a_second_one():
    """★ 「D3 용어집 재사용」 — 새 표를 만들지 않는다(생성과 판정이 같은 표를 본다)."""
    assert "glossary_line" in calls_in(O.color_ko)


def test_a_multi_value_option_waits_for_per_sku_prices():
    """★ 여러 값 = 여러 아이템 = **SKU별 가격**이 필요하다(옵션가를 비율로 매기지 않는다 — 볼트)."""
    attrs = [{"attributeTypeName": "색상", "required": "MANDATORY", "exposed": "EXPOSED"}]
    plan = O.plan_attributes(attrs, {**PRODUCT, "options": [{"name": "색상", "values": ["블랙", "화이트"]}]})
    assert plan["holds"] and "SKU별 가격" in plan["holds"][0]


def test_a_single_value_option_shape_is_read_too():
    """편집기(`_initOptions`)가 받는 단수 `value` 모양도 같은 값이다 — 모양 때문에 「누락」이라 하지 않는다."""
    attrs = [{"attributeTypeName": "사이즈", "required": "MANDATORY", "exposed": "EXPOSED"}]
    plan = O.plan_attributes(attrs, {**PRODUCT, "options": [{"name": "사이즈", "value": "FREE"}]})
    assert plan["attributes"][0]["attributeValueName"] == "FREE" and not plan["holds"]


def test_more_than_three_attributes_is_held():
    """★★ 볼트 실측(카테고리 78293): `len(attributes) > 3`이면 거부 — 보내 봐야 거부다."""
    attrs = [{"attributeTypeName": n, "required": "MANDATORY", "exposed": "EXPOSED"}
             for n in ("가", "나", "다", "라")]
    prod = {**PRODUCT, "attributes": [{"attributeTypeName": n, "attributeValueName": "x"}
                                      for n in ("가", "나", "다", "라")]}
    plan = O.plan_attributes(attrs, prod)
    assert any("3개까지만" in h for h in plan["holds"])


def test_an_unread_meta_is_held():
    plan = O.plan_attributes([], dict(PRODUCT), meta_ok=False)
    assert plan["holds"] and "메타를 읽지 못했습니다" in plan["holds"][0]


def test_a_mandatory_miss_is_held_with_zero_posts(up, monkeypatch):
    """★★★ **오너 계약** — 메타 목에서 누락이 **전송 0회**로 잡힌다."""
    monkeypatch.setattr(up, "overseas_outbound_place_code", OVERSEA)
    posts = _no_post(up, _meta())
    res = up.upload_product(dict(PRODUCT))                                  # 색상 없음
    assert res["held"] is True and "필수 옵션: 색상" in res["error"]
    assert posts == []


# ---------------------------------------------------------------------------
# c) 오류 문장 — `|` 분리 · errorItems 그대로
# ---------------------------------------------------------------------------

def test_pipe_joined_messages_are_split():
    """볼트 실응답 그대로 — 두 사유가 `|`로 붙어 온다."""
    body = ('{"code":"ERROR","message":"유효하지 않은 ISBN 값이 존재합니다.|'
            '유효하지 않은 구매 옵션 값이 존재합니다."}')
    assert O.error_lines(body) == ["유효하지 않은 ISBN 값이 존재합니다.",
                                   "유효하지 않은 구매 옵션 값이 존재합니다."]


def test_item_attribute_messages_are_shown_verbatim():
    body = {"code": "ERROR", "message": "상품 등록 실패", "errorItems": [
        {"itemAttributes": [{"message": "필수 구매 옵션 색상이 없습니다."},
                            {"message": "수량 단위가 올바르지 않습니다."}]}]}
    assert O.error_lines(body) == ["상품 등록 실패", "필수 구매 옵션 색상이 없습니다.",
                                   "수량 단위가 올바르지 않습니다."]


def test_a_rejection_reaches_the_screen_line_by_line(up, monkeypatch):
    monkeypatch.setattr(up, "overseas_outbound_place_code", OVERSEA)
    _no_post(up, _meta())
    body = json.dumps({"code": "ERROR", "message": "A 사유|B 사유"})
    real = up._api_request

    def _api(method, path, data=None):
        if method == "POST":
            return {"error": "쿠팡 거부 — http_status=400", "error_body": body}
        return real(method, path, data)

    up._api_request = _api
    res = up.upload_product({**PRODUCT, "options": [{"name": "색상", "values": ["블랙"]}]})
    assert res["success"] is False and res["error_lines"] == ["A 사유", "B 사유"]


def test_the_lines_survive_the_bridge_and_dispatcher():
    from src.channel_sync._channel_bridge import ChannelUploadError
    from src.seller_console.upload_dispatcher import UploadDispatcher

    def _boom(pd):
        raise ChannelUploadError("쿠팡 업로드 실패: x", lines=["A 사유", "B 사유"])

    with patch("src.channel_sync.coupang_uploader.upload", side_effect=_boom):
        r = UploadDispatcher()._upload_coupang({"title": "t"})
    assert r.details == ["A 사유", "B 사유"] and r.error_code == "api_error"
    # 여러 줄이면 요약은 건수만 — 같은 문장이 요약·목록에 두 번 나오지 않는다(캡처 자기비평).
    assert r.message.endswith("사유 2건(아래)") and "A 사유" not in r.message


# ---------------------------------------------------------------------------
# d) 사전검증 — 등록과 같은 함수
# ---------------------------------------------------------------------------

def test_registration_and_prevalidation_share_one_judge():
    """★★★ 두 자리가 따로 계산하면 **하나는 거짓말을 한다.**"""
    from src.channel_sync import coupang_uploader as bridge
    assert "precheck" in calls_in(CoupangUploader._upload_product_inner)
    assert "precheck" in calls_in(bridge.precheck)


def test_prevalidation_holds_with_details_before_any_post(monkeypatch):
    from src.seller_console.upload_dispatcher import UploadDispatcher
    monkeypatch.setattr("src.seller_console.market_cred_view.coupang_api_state",
                        lambda: {"missing": [], "account": ""})
    monkeypatch.setattr("src.seller_console.market_cred_view.coupang_shipping_state",
                        lambda acct: {"missing": [], "source": ""})
    monkeypatch.setattr("src.channel_sync.coupang_uploader.precheck",
                        lambda pd: {"ok": False, "holds": ["필수 옵션: 색상", "해외 주소지만"], "notes": []})
    [r] = UploadDispatcher().prevalidate({"title": "수행방패", "price": 24000}, ["coupang"])
    assert r.ok is False and r.error_code == "coupang_hold"
    assert r.details == ["필수 옵션: 색상", "해외 주소지만"]
    assert "사유 2건" in r.message and "필수 옵션: 색상" not in r.message


def test_a_single_reason_is_the_summary_itself():
    from src.seller_console.upload_dispatcher import lines_message
    assert lines_message("멈췄습니다", ["필수 옵션: 색상"]) == "멈췄습니다 — 필수 옵션: 색상"


def test_screen_text_carries_no_env_names_or_markdown(up):
    """화면에 나가는 보류 문장 — env 이름·`**`가 없다(F48 캡처에서 둘 다 그대로 보였다)."""
    _code, hold = up.outbound_for_delivery()
    assert hold and "**" not in hold and "_OUTBOUND_SHIPPING_PLACE_CODE" not in hold
    assert "구매대행 출고지 (해외)" in hold          # 연동 화면 라벨 그대로
