"""tests/test_canary8_sku_price.py — 카나리 8차: SKU 추출 파손 + 판매가 0 전송 근원 봉인.

쿠팡 거부 원문의 옵션명 = ``c50ce58d2e5c&ref_=pd_hp_d_atf_ci_mcx_mr_`` — itemName=sku인데 sku가
URL 쿼리 파편이었다(근원: `url[-40:]`). 함께 드러난 판매가 0은 **등록 라우트가 환율을 안 넘겨**
원가 환산이 통째로 실패한 것(검수표 894,000 vs 페이로드 0).

계약(오너 지시 4항):
  1. 로케일·경로·쿼리 무관 ASIN 추출(`/dp/`·`/gp/product/`) — **이 실 URL 전문**으로 고정.
  2. 검수표 판매가가 페이로드 salePrice까지 그대로 도달.
  3. SKU가 유효 식별자 아니면 등록 중단 + 사유("SKU 추출 실패") — 쓰레기 값으로 카나리 안 태운다.
  4. salePrice < 10이면 POST 전 차단(쿠팡 왕복 절약).
"""
from __future__ import annotations

import pytest

from src.collectors.product_key import extract_asin, is_valid_vendor_sku, vendor_sku

# 카나리 8차 실 URL 전문(amazon.de + /-/en/ 로케일 경로 + 긴 쿼리스트링).
CANARY8_URL = ("https://www.amazon.de/-/en/Wireless-Charger/dp/B0GS4698H2/"
               "?_encoding=UTF8&pd_rd_w=c50ce58d2e5c&ref_=pd_hp_d_atf_ci_mcx_mr_")
# 쿠팡이 옵션명으로 거부한 그 값(= 옛 `url[-40:]` 산출물).
REJECTED_ITEM_NAME = "c50ce58d2e5c&ref_=pd_hp_d_atf_ci_mcx_mr_"


# ── 1. ASIN 추출 ────────────────────────────────────────────────────────────────
def test_asin_from_canary8_real_url():
    assert extract_asin(CANARY8_URL) == "B0GS4698H2"
    assert vendor_sku(CANARY8_URL) == "B0GS4698H2"


def test_old_slice_produced_the_rejected_value():
    """근원 재현 — 옛 배선(url[-40:])이 만들던 값이 쿠팡 거부 원문과 일치."""
    assert CANARY8_URL[-40:] == REJECTED_ITEM_NAME
    assert not is_valid_vendor_sku(REJECTED_ITEM_NAME)      # 이제는 게이트에 걸린다


@pytest.mark.parametrize("url,asin", [
    ("https://www.amazon.com/dp/B0GS4698H2", "B0GS4698H2"),
    ("https://www.amazon.co.jp/-/en/gp/product/B08N5WRWNW/?ref_=x&th=1", "B08N5WRWNW"),
    ("https://www.amazon.de/Some-Very-Long-Slug/dp/B012345678/ref=sr_1_3?keywords=x", "B012345678"),
    ("https://www.amazon.co.uk/gp/aw/d/B0ABCDEFGH", "B0ABCDEFGH"),
])
def test_asin_locale_path_query_agnostic(url, asin):
    assert extract_asin(url) == asin


def test_vendor_sku_empty_when_no_identifier():
    """식별자 못 뽑으면 빈값 — 폴백 키(host+path)를 SKU로 쓰지 않는다(쓰레기 전송 금지)."""
    assert vendor_sku("https://example.com/shop/some-page") == ""
    assert vendor_sku("") == ""


def test_valid_vendor_sku_rejects_url_fragments():
    assert is_valid_vendor_sku("B0GS4698H2")
    for bad in (REJECTED_ITEM_NAME, "", "ab", "a b c", "x?y=1", "/dp/B0GS4698H2"):
        assert not is_valid_vendor_sku(bad), bad


# ── 2. 검수표 판매가 → 페이로드 salePrice ────────────────────────────────────────
_DRAFT = {"title_ko": "무선 충전기 스탠드", "price_original": 419.0, "currency": "EUR",
          "images": ["https://m.media-amazon.com/images/I/a.jpg?x=1"],
          "description_html": "<p>상세설명 본문</p>", "brand": "Craighill", "source": "amazon"}


def _review(fx_rates):
    from src.pipeline.register_pipe import build_source_review
    return build_source_review([CANARY8_URL], collect_fn=lambda u: dict(_DRAFT), fx_rates=fx_rates)


def test_fx_missing_makes_price_unset_not_zero_silently():
    """환율 미주입(옛 등록 라우트) = 판매가 미확정. 0원으로 조용히 둔갑하지 않는다."""
    r = _review({})["review_pass"][0]
    assert r["sale_krw"] is None and "환율 미상" in r["cost_basis"]


def test_currency_specific_rate_only():
    """EUR 상품은 EUR 환율로만 환산 — USD 환율 대입(임의 환산) 금지."""
    r = _review({"EUR": 1485.0, "USD": 1370.5})["review_pass"][0]
    assert r["cost_krw"] == round(419.0 * 1485.0)
    r2 = _review({"USD": 1370.5})["review_pass"][0]          # EUR 미수록 → 환산 불가(정직)
    assert r2["sale_krw"] is None


def test_review_price_reaches_payload_saleprice(monkeypatch):
    """검수표 sale_krw → product_data → items[0].salePrice 동일값 도달(키 매칭 봉인)."""
    from src.pipeline.register_pipe import register_source_rows
    rows = _review({"EUR": 1485.0})["review_pass"]
    expected = rows[0]["sale_krw"]
    assert expected and expected > 10

    seen = {}

    def dispatch(product_data, account):
        seen["pd"] = product_data
        up = _uploader(monkeypatch)
        item = up._build_product_payload({
            "title": product_data["title_ko"], "price": int(product_data["sell_price_krw"] or 0),
            "category_id": 1001, "sku": product_data["sku"],
            "description_html": product_data["description_html"],
            "images": product_data["images"], "brand": product_data["brand"],
            "origin": product_data["origin"]})["items"][0]
        seen["item"] = item
        return {"success": True, "product_id": "1"}

    register_source_rows(rows, dispatch_fn=dispatch, approved=True, account="gogane",
                         enrich_fn=lambda r: {"images": _DRAFT["images"],
                                              "description_html": _DRAFT["description_html"],
                                              "category_code": "GEN"})
    assert seen["pd"]["sku"] == "B0GS4698H2"
    assert seen["item"]["salePrice"] == expected
    assert seen["item"]["itemName"] == "B0GS4698H2"
    assert seen["item"]["externalVendorSku"] == "B0GS4698H2"
    # 상세설명 키 정정(구 `description`은 무시돼 제목만 나가던 조용한 누락).
    assert seen["item"]["contents"][0]["contentDetails"][0]["content"] == "<p>상세설명 본문</p>"


def test_pipeline_holds_row_when_price_unset():
    """판매가 미확정 행은 dispatch 자체를 안 한다(0원 전송 = 확정 거부)."""
    from src.pipeline.register_pipe import register_source_rows
    rows = _review({})["review_pass"]
    calls = []
    out = register_source_rows(rows, dispatch_fn=lambda pd, a: calls.append(pd),
                               approved=True, account="gogane",
                               enrich_fn=lambda r: {"images": _DRAFT["images"],
                                                    "description_html": "", "category_code": "GEN"})
    assert calls == []
    assert out["registered"] == 0
    assert "판매가 미확정" in out["results"][0]["reason"]


def test_pipeline_holds_row_when_sku_unextractable():
    from src.pipeline.register_pipe import build_source_review, register_source_rows
    rv = build_source_review(["https://example.com/shop/page"],
                             collect_fn=lambda u: dict(_DRAFT), fx_rates={"EUR": 1485.0})
    calls = []
    out = register_source_rows(rv["review_pass"], dispatch_fn=lambda pd, a: calls.append(pd),
                               approved=True, account="gogane",
                               enrich_fn=lambda r: {"images": _DRAFT["images"],
                                                    "description_html": "", "category_code": "GEN"})
    assert calls == []
    assert "SKU 추출 실패" in out["results"][0]["reason"]


# ── 3·4. 업로더 POST 전 게이트(최후 방어선) ──────────────────────────────────────
def _uploader(monkeypatch):
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
    from src.uploaders.coupang_uploader import CoupangUploader
    return CoupangUploader("ak", "sk", "A01381223", account="gogane", overseas_purchased=True)


def _no_network(up, monkeypatch):
    monkeypatch.setattr(up, "_api_request",
                        lambda *a, **k: pytest.fail("POST 전 차단돼야 하는데 API 호출됨"))


def test_uploader_blocks_garbage_sku(monkeypatch):
    up = _uploader(monkeypatch)
    _no_network(up, monkeypatch)
    res = up.upload_product({"title": "무선 충전기", "price": 894000,
                             "sku": REJECTED_ITEM_NAME, "images": ["https://x/a.jpg"]})
    assert res["success"] is False and res.get("held") is True
    assert "SKU 추출 실패" in res["error"]


def test_uploader_blocks_price_below_10(monkeypatch):
    up = _uploader(monkeypatch)
    _no_network(up, monkeypatch)
    res = up.upload_product({"title": "무선 충전기", "price": 0,
                             "sku": "B0GS4698H2", "images": ["https://x/a.jpg"]})
    assert res["success"] is False and res.get("held") is True
    assert "판매가 미확정" in res["error"]


def test_uploader_gates_pass_with_valid_sku_and_price(monkeypatch):
    """유효 SKU + 정상가면 두 게이트를 통과해 다음 단계(카테고리 예측)로 간다."""
    up = _uploader(monkeypatch)
    monkeypatch.setattr(up, "predict_category", lambda *a, **k: "")   # 다음 게이트에서 정직 중단
    res = up.upload_product({"title": "무선 충전기", "price": 894000,
                             "sku": "B0GS4698H2", "images": ["https://x/a.jpg"]})
    assert res["success"] is False and "카테고리 예측 실패" in res["error"]
