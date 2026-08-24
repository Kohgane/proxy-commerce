"""tests/test_payload_canon_p3.py — 쿠팡 등록 페이로드 **정본**(5,691건 검증) 계약.

오너 SSH 실측(coupang_upload.py:122~145) 전문을 테스트로 고정한다. 카나리 7차 거부
("옵션: 10원 이상의 판매가") 재발 방지 + 다음 세션이 다시 grep하지 않게 구조를 못박는다.
"""
from __future__ import annotations

from datetime import datetime

from src.uploaders.coupang_uploader import CoupangUploader

_SHIP = ("VENDOR_USER_ID", "RETURN_CENTER_CODE", "OUTBOUND_SHIPPING_PLACE_CODE",
         "RETURN_ZIP_CODE", "RETURN_ADDRESS", "RETURN_CHARGE_NAME", "COMPANY_CONTACT_NUMBER")


def _up(monkeypatch):
    for s in _SHIP:
        monkeypatch.setenv(f"COUPANG_{s}", "7437895" if s == "OUTBOUND_SHIPPING_PLACE_CODE" else "x")
    return CoupangUploader(access_key="a", secret_key="b", vendor_id="v")


_PRODUCT = {"title": "TORRAS 갤럭시 케이스", "sku": "SKU-1", "price": 48500,
            "category_id": "1001", "brand": "TORRAS", "origin": "베트남",
            "images": ["https://img/1.jpg?w=500&h=500", "https://img/2.jpg"],
            "description_html": "설명", "tags": ["케이스", "방열"]}


def _payload(monkeypatch):
    return _up(monkeypatch)._build_product_payload(dict(_PRODUCT))


# ── items[] 정본 (7차 거부 지점) ────────────────────────────────────────────────
def test_item_sale_price_present(monkeypatch):
    it = _payload(monkeypatch)["items"][0]
    assert it["salePrice"] == 48500                       # 7차 거부: 옵션 판매가 누락
    assert it["originalPrice"] == int(round(48500 * 1.15 / 100) * 100)   # 정가 15% 상향 반올림
    assert it["originalPrice"] > it["salePrice"]


def test_item_canonical_fields(monkeypatch):
    it = _payload(monkeypatch)["items"][0]
    assert it["itemName"] == "SKU-1" and it["externalVendorSku"] == "SKU-1"   # 정본: itemName=sku
    assert it["maximumBuyCount"] == 3
    assert it["maximumBuyForPerson"] == 0 and it["maximumBuyForPersonPeriod"] == 1
    assert it["outboundShippingTimeDay"] == 7
    assert it["unitCount"] == 1 and it["adultOnly"] == "EVERYONE" and it["taxType"] == "TAX"
    assert it["parallelImported"] == "NOT_PARALLEL_IMPORTED"
    assert it["overseasPurchased"] == "OVERSEAS_PURCHASED" and it["pccNeeded"] is True
    assert it["emptyBarcode"] is True and it["emptyBarcodeReason"] == "구매대행상품 바코드없음"
    assert "emptyBarcodeYn" not in it                      # 구 필드명 폐기


def test_item_certifications_not_required(monkeypatch):
    # 인증 실측 정답 — 추정 문구(env) 대신 NOT_REQUIRED 구조.
    it = _payload(monkeypatch)["items"][0]
    assert it["certifications"] == [{"certificationType": "NOT_REQUIRED", "certificationCode": ""}]


def test_item_search_tags_rule(monkeypatch):
    it = _payload(monkeypatch)["items"][0]
    assert it["searchTags"][:2] == ["TORRAS", "해외직구"]   # [브랜드[:20] or 수입, 해외직구] + 키워드
    assert "케이스" in it["searchTags"] and len(it["searchTags"]) <= 10
    # 브랜드 없으면 '수입'.
    p = dict(_PRODUCT); p["brand"] = ""
    it2 = _up(monkeypatch)._build_product_payload(p)["items"][0]
    assert it2["searchTags"][0] == "수입"


def test_item_images_strip_querystring(monkeypatch):
    imgs = _payload(monkeypatch)["items"][0]["images"]
    assert imgs[0]["vendorPath"] == "https://img/1.jpg"    # 쿼리스트링 제거
    assert imgs[0]["imageType"] == "REPRESENTATION" and imgs[0]["imageOrder"] == 0


def test_item_contents_text(monkeypatch):
    c = _payload(monkeypatch)["items"][0]["contents"][0]
    assert c["contentsType"] == "TEXT" and c["contentDetails"][0]["detailType"] == "TEXT"


# ── 상품 레벨 정본 ──────────────────────────────────────────────────────────────
def test_root_brand_empty_and_product_group_carries_brand(monkeypatch):
    # ★ 정본: brand="" (빈 문자열), 브랜드는 productGroup — 5,691건이 이 형태로 통과.
    p = _payload(monkeypatch)
    assert p["brand"] == "" and p["productGroup"] == "TORRAS"
    assert p["manufacture"] == "TORRAS"


def test_root_sale_dates_and_types(monkeypatch):
    p = _payload(monkeypatch)
    assert p["saleStartedAt"] == datetime.now().strftime("%Y-%m-%dT00:00:00")
    assert p["saleEndedAt"] == "2099-01-01T23:59:59"
    assert p["displayCategoryCode"] == 1001                # int
    assert p["outboundShippingPlaceCode"] == 7437895       # int
    assert len(p["sellerProductName"]) <= 100


def test_root_delivery_canon(monkeypatch):
    p = _payload(monkeypatch)
    assert p["deliveryMethod"] == "AGENT_BUY" and p["deliveryCompanyCode"] == "CJGLS"
    assert p["deliveryChargeType"] == "FREE" and p["deliveryCharge"] == 0
    assert p["freeShipOverAmount"] == 0 and p["deliveryChargeOnReturn"] == 5000
    assert p["remoteAreaDeliverable"] == "N" and p["unionDeliveryType"] == "NOT_UNION_DELIVERY"
    assert p["returnCharge"] == 5000 and p["requested"] is True


def test_return_address_from_env_not_script(monkeypatch):
    # 오너 지시: 스크립트 하드코딩 주소/우편번호(14548)는 승계 금지 — env가 정본.
    for s_ in _SHIP:
        monkeypatch.setenv(f"COUPANG_{s_}", "x")
    monkeypatch.setenv("COUPANG_RETURN_ZIP_CODE", "06000")     # env가 정본(_up 헬퍼 뒤에 설정)
    monkeypatch.setenv("COUPANG_RETURN_ADDRESS", "서울시 강남구")
    up = CoupangUploader(access_key="a", secret_key="b", vendor_id="v")
    p = up._build_product_payload(dict(_PRODUCT))
    assert p["returnZipCode"] == "06000" and p["returnAddress"] == "서울시 강남구"
    src = open("src/uploaders/coupang_uploader.py", encoding="utf-8").read()
    assert "14548" not in src                              # 스크립트 하드코딩 미승계


# ── 등록 후 2단계(승인요청) ─────────────────────────────────────────────────────
def test_approval_requested_after_register(monkeypatch):
    up = _up(monkeypatch)
    calls = []
    def _api(m, p, data=None):
        calls.append((m, p))
        if "predict" in p:
            return {"data": {"predictedCategoryId": "1001"}}
        if m == "POST" and p.endswith("seller-products"):
            return {"data": 777, "code": "SUCCESS"}
        if m == "PUT" and "approvals" in p:
            return {"code": "SUCCESS"}
        return {}
    monkeypatch.setattr(up, "_api_request", _api)
    monkeypatch.setattr("time.sleep", lambda s: None)
    r = up.upload_product(dict(_PRODUCT))
    assert r["success"] is True and r["product_id"] == "777"
    assert r["approval_requested"] is True                 # SAVED 방치 방지
    assert any(m == "PUT" and "approvals" in p for m, p in calls)


def test_category_predict_failure_stops_registration(monkeypatch):
    # 정본: cat 없으면 FAIL — 임의 카테고리 전송 금지.
    up = _up(monkeypatch)
    posted = {"n": 0}
    def _api(m, p, data=None):
        if "predict" in p:
            return {}                                       # 예측 실패
        if m == "POST":
            posted["n"] += 1
        return {}
    monkeypatch.setattr(up, "_api_request", _api)
    p = dict(_PRODUCT); p["category_id"] = ""
    r = up.upload_product(p)
    assert r["success"] is False and r.get("held") is True
    assert "카테고리" in r["error"] and posted["n"] == 0
