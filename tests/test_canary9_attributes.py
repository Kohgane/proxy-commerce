"""tests/test_canary9_attributes.py — 카나리 9차: attributes(필수 구매 옵션) 정본 승계.

쿠팡 거부: "필수 구매 옵션 (미입력시 등록/노출 제한) 존재하지 않습니다."
실측 근원: `attributes` 를 채우는 코드가 **어디에도 없어** 페이로드가 항상 빈 배열이었다.

정본 = 오너 SSH 실측 `build_opt.py::attr_safe`(L8~35, 2026-08-12 실증, 5,691건 통과).
처방은 **삭제가 아니라 실값 대체**(반려 처리 표준) — 이 파일이 그 규칙을 고정한다.
"""
from __future__ import annotations

import pytest

from src.uploaders.coupang_uploader import CoupangUploader as CU


# ── attr_safe 정본 규칙 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["", "없음", "-", "None", "null",
                                 "상세설명 참조", "상세페이지 참조", "상세참조"])
def test_bad_values_all_replaced(bad):
    """BAD 값은 전량 대체 — 특히 '상세설명 참조' 계열은 쿠팡이 거부한다(실증). 전송 금지."""
    out = CU.attr_safe([{"attributeTypeName": "색상", "attributeValueName": bad}], "Blue Wallet")
    assert out[0]["attributeValueName"] == "Blue"
    assert out[0]["attributeValueName"] not in CU.ATTR_BAD_VALUES


def test_gtin_attribute_skipped():
    out = CU.attr_safe([{"attributeTypeName": "gtin", "attributeValueName": "0123456789"},
                        {"attributeTypeName": "GTIN 코드", "attributeValueName": "x"},
                        {"attributeTypeName": "수량", "attributeValueName": "2"}], "상품")
    assert [a["attributeTypeName"] for a in out] == ["수량"]
    assert out[0]["attributeValueName"] == "2"          # 정상 값은 보존(대체 안 함)


def test_empty_result_falls_back_to_quantity_one():
    """결과가 비면 반드시 [{수량:1}] — 빈 배열 전송이 9차 거부의 직접 원인."""
    assert CU.attr_safe([], "상품") == [{"attributeTypeName": "수량", "attributeValueName": "1"}]
    only_gtin = CU.attr_safe([{"attributeTypeName": "gtin", "attributeValueName": "1"}], "상품")
    assert only_gtin == [{"attributeTypeName": "수량", "attributeValueName": "1"}]


def test_duplicate_type_name_keeps_first():
    out = CU.attr_safe([{"attributeTypeName": "색상", "attributeValueName": "Red"},
                        {"attributeTypeName": "색상", "attributeValueName": "Blue"}], "상품")
    assert len(out) == 1 and out[0]["attributeValueName"] == "Red"


def test_value_truncated_to_28_and_exposed_preserved():
    out = CU.attr_safe([{"attributeTypeName": "색상", "attributeValueName": "가" * 40,
                         "exposed": "EXPOSED"}], "상품")
    assert len(out[0]["attributeValueName"]) == 28 == CU.ATTR_VALUE_MAX
    assert out[0]["exposed"] == "EXPOSED"
    # exposed 없으면 키 자체를 만들지 않는다(원본 보존만).
    assert "exposed" not in CU.attr_safe([{"attributeTypeName": "색상",
                                           "attributeValueName": "Red"}], "상품")[0]


# ── 상품명 실값 추출 + 속성별 기본값(정본 표) ────────────────────────────────────
@pytest.mark.parametrize("type_name,product_name,expected", [
    ("색상", "Navy Blue Leather Bag", "Navy"),               # 정규식 첫 매칭
    ("색상", "Craighill Stainless Charger", "블랙"),          # ★ Stainless는 목록에 없다 → 기본값
    ("색상", "무선 충전기", "블랙"),
    ("신발사이즈", "러닝화 270 남성", "270"),
    ("신발사이즈", "러닝화", "260"),                          # ※ FREE 아님(쿠팡 거부)
    ("펜촉", "만년필 EF 닙", "EF"),
    ("굵기", "만년필", "M"),
    ("수량", "아무거나", "1"),
    ("개수", "아무거나", "1"),
    ("중량", "아무거나", "100"),
    ("무게", "아무거나", "100"),
    ("세트구성", "아무거나", "단품"),
    ("구성품", "아무거나", "본품"),
    ("사이즈", "아무거나", "FREE"),
    ("크기", "아무거나", "FREE"),
    ("소재", "아무거나", "기타"),                              # 그 외
])
def test_default_value_table(type_name, product_name, expected):
    out = CU.attr_safe([{"attributeTypeName": type_name, "attributeValueName": ""}], product_name)
    assert out[0]["attributeValueName"] == expected


def test_shoe_size_free_is_rejected_and_replaced():
    """신발사이즈 FREE/프리는 BAD가 아니어도 대체한다(쿠팡 거부 실증)."""
    for v in ("FREE", "free", "프리"):
        out = CU.attr_safe([{"attributeTypeName": "신발사이즈", "attributeValueName": v}], "러닝화 280")
        assert out[0]["attributeValueName"] == "280"
    # 일반 '사이즈'는 FREE가 정상값이라 보존한다(신발사이즈만 특례).
    keep = CU.attr_safe([{"attributeTypeName": "사이즈", "attributeValueName": "FREE"}], "가방")
    assert keep[0]["attributeValueName"] == "FREE"


# ── 카테고리 메타 스키마 → build_attrs → 페이로드 ───────────────────────────────
_META = {"data": {"attributes": [
    {"attributeTypeName": "수량", "dataType": "NUMBER", "required": "MANDATORY", "exposed": "EXPOSED"},
    {"attributeTypeName": "색상", "dataType": "STRING", "required": "MANDATORY", "exposed": "EXPOSED"},
    {"attributeTypeName": "gtin", "dataType": "STRING", "required": "MANDATORY", "exposed": "NONE"},
    {"attributeTypeName": "소재", "dataType": "STRING", "required": "OPTIONAL", "exposed": "EXPOSED"}],
    "noticeCategories": [{"noticeCategoryName": "기타 재화",
                          "noticeCategoryDetailNames": [{"noticeCategoryDetailName": "품명 및 모델명"}]}]}}


def _up(monkeypatch, meta=None):
    for k, v in {
        "COUPANG_GOGANE_OUTBOUND_SHIPPING_PLACE_CODE": "1",
        "COUPANG_GOGANE_RETURN_CENTER_CODE": "R1",
        "COUPANG_GOGANE_RETURN_ZIP_CODE": "12345",
        "COUPANG_GOGANE_RETURN_ADDRESS": "서울시",
        "COUPANG_GOGANE_RETURN_CHARGE_NAME": "담당자",
        "COUPANG_GOGANE_COMPANY_CONTACT_NUMBER": "02-000-0000",
        "COUPANG_GOGANE_VENDOR_USER_ID": "gogane01",
    }.items():
        monkeypatch.setenv(k, v)
    up = CU("ak", "sk", "A01381223", account="gogane", overseas_purchased=True)
    monkeypatch.setattr(up, "_api_request", lambda *a, **k: (meta if meta is not None else _META))
    return up


_PRODUCT = {"title": "Craighill Stainless Wireless Charger", "price": 894000,
            "category_id": 1001, "sku": "B0GS4698H2", "images": ["https://x/a.jpg"],
            "brand": "Craighill", "origin": "미국"}


def test_attribute_schema_parsed_from_category_meta(monkeypatch):
    sch = _up(monkeypatch).get_category_attribute_schema("1001")
    by = {s["attributeTypeName"]: s for s in sch}
    assert by["수량"]["required"] is True and by["소재"]["required"] is False
    assert by["gtin"]["exposed"] == "NONE"


def test_category_meta_fetched_once_for_notices_and_attrs(monkeypatch):
    """고시정보+속성은 같은 응답 — 카테고리당 1회만 호출한다(왕복 절약·스키마 불일치 0)."""
    up = _up(monkeypatch)
    calls = []
    monkeypatch.setattr(up, "_api_request", lambda *a, **k: (calls.append(a), _META)[1])
    up.get_category_notice_schema("1001")
    up.get_category_attribute_schema("1001")
    up.get_category_attribute_schema("1001")
    assert len(calls) == 1


def test_payload_attributes_filled_from_schema(monkeypatch):
    """9차 근원 봉인: 상품이 attributes를 안 줘도 페이로드가 비지 않는다."""
    up = _up(monkeypatch)
    assert _PRODUCT.get("attributes") is None                     # 파이프라인은 이 키를 안 준다
    attrs = up._build_product_payload(
        _PRODUCT, attr_schema=up.get_category_attribute_schema("1001"))["items"][0]["attributes"]
    assert attrs, "빈 배열 전송 = 카나리 9차 거부"
    got = {a["attributeTypeName"]: a["attributeValueName"] for a in attrs}
    assert got == {"수량": "1", "색상": "블랙"}                    # Stainless → 기본값 경로
    assert "gtin" not in got
    assert all(a["attributeValueName"] not in CU.ATTR_BAD_VALUES for a in attrs)


def test_product_supplied_attrs_win_over_schema_defaults(monkeypatch):
    up = _up(monkeypatch)
    p = {**_PRODUCT, "attributes": [{"attributeTypeName": "색상", "attributeValueName": "Gold"}]}
    got = {a["attributeTypeName"]: a["attributeValueName"]
           for a in up.build_attrs(p, up.get_category_attribute_schema("1001"))}
    assert got["색상"] == "Gold" and got["수량"] == "1"


def test_no_meta_still_sends_fallback(monkeypatch):
    """메타 조회 실패(빈 스키마)여도 빈 배열은 안 나간다."""
    up = _up(monkeypatch, meta={"data": {}})
    attrs = up._build_product_payload(_PRODUCT, attr_schema=[])["items"][0]["attributes"]
    assert attrs == [{"attributeTypeName": "수량", "attributeValueName": "1"}]


# ── 게이트: 필수 속성 미충족이면 POST 전 차단(택배사·SKU 게이트와 동형) ───────────
def test_missing_required_attrs_names_the_gap(monkeypatch):
    up = _up(monkeypatch)
    sch = up.get_category_attribute_schema("1001")
    unmet = up.missing_required_attrs([{"attributeTypeName": "수량", "attributeValueName": "1"}], sch)
    assert unmet == ["색상"]                                     # gtin은 전송 대상 아님 → 제외
    assert up.missing_required_attrs(up.build_attrs(_PRODUCT, sch), sch) == []


def test_upload_blocks_before_post_when_required_attr_unmet(monkeypatch):
    up = _up(monkeypatch)
    monkeypatch.setattr(up, "predict_category", lambda *a, **k: "1001")
    monkeypatch.setattr(up, "build_attrs", lambda *a, **k: [])   # 인위적 미충족(회귀 재현)
    monkeypatch.setattr(up, "_api_request", _fail_on_post(up))
    res = up.upload_product(dict(_PRODUCT))
    assert res["success"] is False and res.get("held") is True
    assert "필수 구매 옵션 미충족" in res["error"] and "색상" in res["error"]


def _fail_on_post(up):
    def _req(method, path, *a, **k):
        if str(method).upper() == "POST" and "seller-products" in str(path):
            pytest.fail("POST 전 차단돼야 하는데 등록 호출됨")
        return _META
    return _req


def test_upload_proceeds_to_post_when_attrs_ok(monkeypatch):
    """정상 경로 회귀: 속성이 채워지면 등록 POST까지 간다(과잉 차단 0)."""
    up = _up(monkeypatch)
    monkeypatch.setattr(up, "predict_category", lambda *a, **k: "1001")
    sent = {}

    def _req(method, path, data=None, **k):
        if str(method).upper() == "POST" and "seller-products" in str(path):
            sent["payload"] = data
            return {"code": "SUCCESS", "data": 12345}
        if str(method).upper() == "PUT":
            return {"code": "SUCCESS"}
        return _META

    monkeypatch.setattr(up, "_api_request", _req)
    monkeypatch.setattr("time.sleep", lambda s: None)
    res = up.upload_product(dict(_PRODUCT))
    assert res["success"] is True and res["product_id"] == "12345"
    assert sent["payload"]["items"][0]["attributes"] == [
        {"attributeTypeName": "수량", "attributeValueName": "1", "exposed": "EXPOSED"},
        {"attributeTypeName": "색상", "attributeValueName": "블랙", "exposed": "EXPOSED"}]
