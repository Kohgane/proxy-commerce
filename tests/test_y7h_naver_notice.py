"""Y7-H(오너 2026-10-09 19:46 KST, 플리츠 세트 · 셰고가) — 네이버 상품정보제공고시 + 필수 칸 전수 표.

증거: 등록 400 invalidInputs
  - `originProduct.detailAttribute.productInfoProvidedNotice.etc.itemName` 품명 50자 미만
  - `originProduct.detailAttribute.productInfoProvidedNotice.etc.manufacturer` 제조자 입력
원인(코드): 고시를 템플릿(ETC) 위에 네 칸만 덮었다 — 품명 = 「[해외직구] + 상품명」[:100], 제조자 = 수집 브랜드(비어 있음).

계약
- 타입은 카테고리로: 패션의류 → WEAR(의류 칸 전부), 그 밖 → ETC. 블록은 통째로 우리 것(템플릿 예시값 0).
- 구매대행 기본값(설정에서 바꿈): 상세페이지 참조 · 제조국 중국(중국 소싱처) · 공통 문구 5종.
- 품명·모델명 = 50자 이내 짧은 이름(쿠팡용) — **자르지 않는다**. 없으면 사전검증 `naver_required_itemName`.
- 사전검증이 등록과 같은 조립으로 필수 칸 전수 표를 재고, 채울 수 없는 칸만 `naver_required_<칸>`.
"""
from __future__ import annotations

import json

import pytest

from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS

TITLE = "플리츠 미니멀 여성 여름 세트, 디자인 감각이 돋보이는 언밸런스 컷팅 주름 상의와 스커트 투피스 세트"
BODY_19_46 = json.dumps({"code": "InvalidInput", "message": "요청 값이 올바르지 않습니다.", "invalidInputs": [
    {"name": "originProduct.detailAttribute.productInfoProvidedNotice.etc.itemName", "type": "Size",
     "message": "품명 항목은 50자 미만으로 입력해 주세요."},
    {"name": "originProduct.detailAttribute.productInfoProvidedNotice.etc.manufacturer", "type": "NotBlank",
     "message": "제조자 항목을 입력해 주세요."}]}, ensure_ascii=False)


@pytest.fixture
def fashion(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")                # 사전검증은 키 점검이 먼저 — 여기선 있는 상태로
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    import src.uploaders.naver_categories as NC
    monkeypatch.setattr(NC, "name_of", lambda cid: {"50000816": "패션의류>여성의류>정장세트",
                                                    "50000570": "패션잡화>패션소품>키링"}.get(str(cid), ""))
    import src.uploaders.naver_notice as NN
    monkeypatch.setattr(NN, "get_settings", lambda *a, **k: dict(NN.DEFAULTS))
    return NN


def _pleats(**over):
    pd = {"title_ko": TITLE, "coupang_name": "플리츠 미니멀 여성 여름 세트 디자인", "sell_price_krw": 52000,
          "images": ["https://img.alicdn.com/a.jpg"], "description_html": "<p>본문</p>", "naver_category_id": "50000816",
          "item_id": "it-7h", "url": "https://detail.tmall.com/item.htm?id=1", "brand": ""}
    pd.update(over)
    return pd


def _payload(pd):
    from src.channel_sync._channel_bridge import to_collected
    up = SS(account="chezgoga")
    return up._build_product_payload(up.prepare_product(to_collected(pd)))


def test_1946_item_goes_as_wear_with_every_field(fashion):
    body = _payload(_pleats())
    n = body["originProduct"]["detailAttribute"]["productInfoProvidedNotice"]
    assert n["productInfoProvidedNoticeType"] == "WEAR" and set(n) == {"productInfoProvidedNoticeType", "wear"}
    w = n["wear"]
    assert set(fashion.REQUIRED["WEAR"]) <= set(w) and all(str(w[k]).strip() for k in fashion.REQUIRED["WEAR"])
    assert w["manufacturer"] == "상세페이지 참조 (제조국: 중국)"           # 19:46 빈 제조자 → 기본값
    assert w["material"] == w["color"] == w["size"] == w["caution"] == w["packDateText"] == "상세페이지 참조"
    assert w["afterServiceDirector"] == "010-0000-0000"
    assert "HARVEST" not in json.dumps(body, ensure_ascii=False) and SS.find_template_leaks(body) == []
    from src.uploaders import naver_required as NR
    assert NR.missing(body) == []                                            # 전수 표 빈칸 0


def test_other_categories_go_as_etc_with_short_name_not_cut(fashion):
    body = _payload(_pleats(naver_category_id="50000570"))
    n = body["originProduct"]["detailAttribute"]["productInfoProvidedNotice"]
    assert n["productInfoProvidedNoticeType"] == "ETC"
    e = n["etc"]
    assert e["itemName"] == e["modelName"] == "플리츠 미니멀 여성 여름 세트 디자인"     # 쿠팡용 짧은 이름(50자 이내)
    assert "[해외직구]" not in e["itemName"]
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE
    assert e["certificateDetails"] == PURCHASE_AGENT_NOTICE                   # KC: 구매대행 고지와 같은 글
    assert e["manufacturer"] == "상세페이지 참조 (제조국: 중국)"


def test_collected_brand_is_the_manufacturer(fashion):
    e = _payload(_pleats(naver_category_id="50000570", brand="Fellow",
                         url="https://www.amazon.com/dp/B0", images=["https://m.media-amazon.com/x.jpg"]))
    assert e["originProduct"]["detailAttribute"]["productInfoProvidedNotice"]["etc"]["manufacturer"] == "Fellow"


def test_no_short_name_is_held_not_cut(fashion):
    """50자 넘는 이름만 있으면 비워 두고 사전검증이 보류 — 자르지 않는다."""
    long = "가" * 51
    body = _payload(_pleats(naver_category_id="50000570", coupang_name="", title_ko=long))
    e = body["originProduct"]["detailAttribute"]["productInfoProvidedNotice"]["etc"]
    assert e["itemName"] == "" and e["modelName"] == ""
    from src.uploaders import naver_required as NR
    assert {m["field"] for m in NR.missing(body)} >= {"itemName", "modelName"}
    from src.seller_console.upload_dispatcher import naver_payload_holds
    holds = naver_payload_holds(_pleats(naver_category_id="50000570", coupang_name="", title_ko=long, title=long), "it-7h")
    codes = [h["code"] for h in holds]
    assert "naver_required_itemName" in codes
    h = next(x for x in holds if x["code"] == "naver_required_itemName")
    assert h["action_url"] == "/seller/collect/preview/it-7h" and "50자" in h["line"]


def test_missing_as_phone_is_one_hold_line(fashion, monkeypatch):
    monkeypatch.delenv("NAVER_AS_PHONE", raising=False)
    from src.seller_console.upload_dispatcher import naver_payload_holds
    holds = naver_payload_holds(_pleats(), "it-7h")
    assert [h["code"] for h in holds] == ["naver_required_afterServiceTelephoneNumber"]
    assert holds[0]["action_url"] == "/seller/markets/connect/smartstore"


def test_settings_change_the_defaults(fashion, monkeypatch):
    NN = fashion
    monkeypatch.setattr(NN, "get_settings", lambda *a, **k: {**NN.DEFAULTS, "detail_ref": "상품 상세 참고",
                                                             "return_cost_reason": "왕복 배송비 구매자 부담"})
    w = _payload(_pleats())["originProduct"]["detailAttribute"]["productInfoProvidedNotice"]["wear"]
    assert w["material"] == "상품 상세 참고" and w["returnCostReason"] == "왕복 배송비 구매자 부담"


def test_settings_save_validates_length_and_scope():
    from src.uploaders import naver_notice as NN
    with pytest.raises(ValueError):
        NN.save_settings("y7h", {"manufacturer": "가" * 201}, shared=False)
    st = NN.save_settings("y7h", {"origin_cn": "중국(구매대행)"}, shared=False)
    assert st["origin_cn"] == "중국(구매대행)" and st["detail_ref"] == "상세페이지 참조"
    assert NN.get_settings("someone-else", shared=False)["origin_cn"] == "중국"


def test_settings_page_saves(fashion):
    from src.order_webhook import app
    import src.uploaders.naver_notice as NN
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="y7h-page", user_email="y7h-page@example.com", user_role="seller")
    html = c.get("/seller/settings/naver-notice").get_data(as_text=True)
    assert 'data-role="naver-notice-settings"' in html and "상세페이지 참조" in html
    r = c.post("/seller/settings/naver-notice", data={"origin_cn": "중국 본토"})
    assert r.status_code == 200 and "저장했어요" in r.get_data(as_text=True)
    from importlib import reload
    reload(NN)
    assert NN.get_settings("y7h-page", shared=False)["origin_cn"] == "중국 본토"


def test_1946_400_maps_to_notice_settings():
    from src.uploaders import naver_invalid as NI
    rows = NI.rows(BODY_19_46, "it-7h")
    assert [r["action_url"] for r in rows] == ["/seller/settings/naver-notice"] * 2
    assert all(r["action_label"] == "고시 기본값 →" for r in rows)


def test_prevalidate_and_registration_use_the_same_assembly(fashion):
    """사전검증 전수 표는 등록과 **같은 조립**(`_payload_for_market` → bridge → prepare_product → `_build_product_payload`)."""
    from src.seller_console.upload_dispatcher import naver_payload_holds
    assert naver_payload_holds(_pleats(), "it-7h") == []
