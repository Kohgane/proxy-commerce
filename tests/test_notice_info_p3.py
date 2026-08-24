"""tests/test_notice_info_p3.py — P3 카나리 반려: 고시정보 실값 배선.

쿠팡 거부 원문: '기타 재화' 불가 + 카테고리상세명 실값 요구. 카테고리 메타 API로 고시정보 유형 동적 결정,
실값 채움(제조자/수입자/원산지/AS/인증), 원산지 미확인 등록 보류, 검수표 미리보기. 오프라인(_api_request 주입).
"""
from __future__ import annotations

from src.uploaders.coupang_uploader import CoupangUploader
from src.pipeline import register_pipe as RP

# 쿠팡 카테고리 메타 API 응답(고시정보 스키마) — 폰 액세서리 예.
_META = {"data": {"noticeCategories": [{
    "noticeCategoryName": "휴대폰/스마트기기 액세서리",
    "noticeCategoryDetailNames": [
        {"noticeCategoryDetailName": "품명 및 모델명"},
        {"noticeCategoryDetailName": "제조자(수입자)"},
        {"noticeCategoryDetailName": "제조국"},
        {"noticeCategoryDetailName": "법에 의한 인증·허가 사항"},
        {"noticeCategoryDetailName": "A/S 책임자와 전화번호"},
    ]}]}}


def _up(account="gogane"):
    return CoupangUploader(access_key="a", secret_key="b", vendor_id="v", account=account,
                           overseas_purchased=True)


def test_notice_schema_from_meta_api(monkeypatch):
    u = _up()
    monkeypatch.setattr(u, "_api_request",
                        lambda m, p, data=None: _META if "category-related-metas" in p else {})
    schema = u.get_category_notice_schema("1001")
    assert schema and schema[0]["noticeCategoryName"] == "휴대폰/스마트기기 액세서리"   # 기타 재화 아님
    assert "제조국" in schema[0]["details"] and "품명 및 모델명" in schema[0]["details"]


def test_build_notices_real_values(monkeypatch):
    u = _up(); u.company_contact = "02-1234-5678"
    sch = [{"noticeCategoryName": "휴대폰/스마트기기 액세서리",
            "details": [d["noticeCategoryDetailName"] for d in _META["data"]["noticeCategories"][0]["noticeCategoryDetailNames"]]}]
    notices, hold = u._build_notices({"title": "TORRAS 갤럭시 케이스", "brand": "TORRAS", "origin": "베트남"}, sch)
    assert hold is None
    by = {n["noticeCategoryDetailName"]: n["content"] for n in notices}
    assert all(n["noticeCategoryName"] == "휴대폰/스마트기기 액세서리" for n in notices)   # 실 유형
    assert "TORRAS" in by["제조자(수입자)"] and "고가네" in by["제조자(수입자)"]          # 제조자=브랜드·수입자=상호
    assert by["제조국"] == "베트남"                                                       # 원산지=수집값
    assert "1234" in by["A/S 책임자와 전화번호"]                                          # env 연락처
    assert by["법에 의한 인증·허가 사항"] == u.cert_none_text                             # 표준 문구
    assert by["품명 및 모델명"] == "TORRAS 갤럭시 케이스"


def test_origin_unverified_holds():
    u = _up()
    sch = [{"noticeCategoryName": "X", "details": ["제조국", "제조자(수입자)"]}]
    notices, hold = u._build_notices({"title": "케이스", "brand": "TORRAS", "origin": ""}, sch)
    assert hold and "원산지" in hold                                    # 미확인 → 보류(추정 금지)
    # 원산지 있으면 통과.
    _, hold2 = u._build_notices({"title": "케이스", "brand": "TORRAS", "origin": "중국"}, sch)
    assert hold2 is None


def test_importer_name_by_account():
    assert _up("gogane").importer_name == "고가네" and _up("woojoo").importer_name == "우주대행"


def test_fallback_to_etc_when_schema_absent():
    u = _up()
    notices, _ = u._build_notices({"title": "x", "brand": "B", "origin": "중국"}, None)   # 스키마 미주입
    assert notices and notices[0]["noticeCategoryName"] == "기타 재화"   # 폴백(네트워크 0)


def test_upload_product_holds_when_origin_missing(monkeypatch):
    # 배송 env 충족 + 메타 스키마 + 원산지 없음 → 등록 보류(쿠팡 POST 호출 0). account 미지정=무접두 배송 env.
    for s in ("VENDOR_USER_ID", "RETURN_CENTER_CODE", "OUTBOUND_SHIPPING_PLACE_CODE",
              "RETURN_ZIP_CODE", "RETURN_ADDRESS", "RETURN_CHARGE_NAME", "COMPANY_CONTACT_NUMBER"):
        monkeypatch.setenv(f"COUPANG_{s}", "x")
    u = CoupangUploader(access_key="a", secret_key="b", vendor_id="v")
    called = {"post": False}
    def _api(m, p, data=None):
        if "categorization/predict" in p:
            return {"data": {"predictedCategoryId": "1001"}}
        if "category-related-metas" in p:
            return _META
        if m == "POST" and "seller-products" in p:
            called["post"] = True
            return {"data": 1, "code": "SUCCESS"}
        return {}
    monkeypatch.setattr(u, "_api_request", _api)
    res = u.upload_product({"title": "케이스", "brand": "TORRAS", "origin": "", "sku": "s", "images": ["u"]})
    assert res["success"] is False and res.get("held") is True and called["post"] is False   # 등록 시도 0
    assert "원산지" in res["error"] or "미확인" in res["error"]
    # 원산지 있으면 등록 진행(POST 호출).
    called["post"] = False
    res2 = u.upload_product({"title": "케이스", "brand": "TORRAS", "origin": "베트남", "sku": "s", "images": ["u"]})
    assert res2["success"] is True and called["post"] is True


def test_predict_category_used_for_display_code(monkeypatch):
    # 예측 카테고리 실 리프 ID가 displayCategoryCode + 고시정보 스키마 조회에 쓰인다.
    for s in ("VENDOR_USER_ID", "RETURN_CENTER_CODE", "OUTBOUND_SHIPPING_PLACE_CODE",
              "RETURN_ZIP_CODE", "RETURN_ADDRESS", "RETURN_CHARGE_NAME", "COMPANY_CONTACT_NUMBER"):
        monkeypatch.setenv(f"COUPANG_{s}", "x")
    u = CoupangUploader(access_key="a", secret_key="b", vendor_id="v")
    sent = {}
    def _api(m, p, data=None):
        if "categorization/predict" in p:
            return {"data": {"predictedCategoryId": "556677"}}
        if "category-related-metas" in p:
            return _META
        if m == "POST" and "seller-products" in p:
            sent["payload"] = data
            return {"data": 1, "code": "SUCCESS"}
        return {}
    monkeypatch.setattr(u, "_api_request", _api)
    u.upload_product({"title": "케이스", "brand": "B", "origin": "베트남", "sku": "s", "images": ["u"]})
    assert sent["payload"]["displayCategoryCode"] == "556677"           # 예측 코드 사용
    assert sent["payload"]["items"][0]["notices"][0]["noticeCategoryName"] == "휴대폰/스마트기기 액세서리"


# ── 검수표 고시정보 미리보기(등록 전 오너 확인) ──────────────────────────────────
def test_review_row_notice_preview():
    r = RP.build_source_review_row({"title_ko": "TORRAS 케이스", "brand": "TORRAS",
                                    "origin": "베트남", "currency": "KRW", "price_original": 30000})
    np = r["notice_preview"]
    assert np["제조자"] == "TORRAS" and np["수입자"] == "고가네" and np["origin_verified"] is True
    assert r["notice_hold"] is False and r["brand"] == "TORRAS" and r["origin"] == "베트남"
    # 원산지 미확인 → 보류 표기.
    r2 = RP.build_source_review_row({"title_ko": "케이스", "currency": "KRW", "price_original": 30000})
    assert r2["notice_hold"] is True and r2["notice_preview"]["origin_verified"] is False
    assert "보류" in r2["notice_preview"]["원산지"]
