"""tests/test_markets_guide.py — 인앱 마켓 API 키 발급 가이드 검증."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_guide_data_covers_all_connect_markets():
    from src.seller_console.market_guide import get_guide
    from src.seller_console.market_credentials import SUPPORTED_MARKETS
    keys = {g["key"] for g in get_guide()}
    assert set(SUPPORTED_MARKETS).issubset(keys)


def test_guide_includes_global_expansion_markets():
    from src.seller_console.market_guide import get_guide
    keys = {g["key"] for g in get_guide()}
    assert {"amazon", "ebay", "shopee"}.issubset(keys)
    planned = {g["key"] for g in get_guide() if g.get("status") == "planned"}
    # K2에서 톡스토어(연동대행사)가 planned로 합류 — 대행사 승인 전이라 등록이 안 열린다.
    assert planned == {"amazon", "ebay", "shopee", "talkstore"}


def test_guide_entries_have_required_shape():
    from src.seller_console.market_guide import get_guide
    for g in get_guide():
        # `official_url`은 **있으면** http여야 한다. 없을 수도 있다 — 발급 경로가 아직
        # 공개 확인되지 않은 마켓(톡스토어)에 **없는 링크를 지어 넣지 않기** 위함이다.
        if g.get("official_url"):
            assert g["official_url"].startswith("http"), g["key"]
        assert g["flow"] and g["steps"] and g["fields"]
        for fld in g["fields"]:
            assert fld["env"] and fld["label"]


class TestGuidePage:
    def test_guide_page_200_with_image_and_sections(self, client):
        resp = client.get("/seller/markets/guide")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "<svg" in html  # 개념 일러스트(이미지)
        assert "guide-stepper" in html  # 시각 흐름
        for key in ("coupang", "smartstore", "elevenst", "shopify", "woocommerce"):
            assert f"guide-{key}" in html
        assert "COUPANG_ACCESS_KEY" in html

    def test_guide_page_shows_coupang_shipping_section(self, client):
        """쿠팡 출고지·반품지 안내가 그림+예시와 함께 노출되어야 한다."""
        html = client.get("/seller/markets/guide").get_data(as_text=True)
        # 등록 거부 원인이었던 핵심 env들이 가이드에 예시와 함께 표시
        assert "COUPANG_RETURN_CENTER_CODE" in html
        assert "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE" in html
        assert "COUPANG_VENDOR_USER_ID" in html
        assert "출고지" in html and "반품지" in html
        assert "1000274592" in html  # 예시 코드

    def test_markets_page_has_guide_button(self, client):
        html = client.get("/seller/markets").get_data(as_text=True)
        assert "/seller/markets/guide" in html

    def test_connect_page_has_guide_button(self, client):
        html = client.get("/seller/markets/connect").get_data(as_text=True)
        assert "/seller/markets/guide" in html
