"""tests/test_v86_o_shopify_woo_detail.py — v86-O: Shopify·WooCommerce 상세페이지 소비 배선.

v86-N은 description_html을 읽는 마켓(쿠팡/스스/11번가)만 배선. 감사서 발견한 별건 갭:
- Shopify: _upload_shopify가 plain description만 읽어 블록/HTML 미반영.
- WooCommerce: _generate_description이 항상 벤더 템플릿만 생성 → 셀러 상세 전면 유실.

수리: Shopify는 description_html 우선(→ body_html). WooCommerce는 셀러 상세를 본문으로,
컴플라이언스 안내(배송·관부가세·교환반품)는 하단 유지. 블록/설명 없으면 기존 폴백(회귀 0).
"""
from __future__ import annotations

from src.seller_console import upload_dispatcher as mod
from src.channel_sync._channel_bridge import to_collected
from src.vendors import woocommerce_client as wc


def _dispatch_shopify_capture(monkeypatch, product):
    """FakeAdapter로 Shopify에 전달된 ListingPayload를 포획."""
    captured = {}

    class _FakeAdapter:
        def validate_listing(self, payload):
            from src.markets.adapters.base import ListingResult
            return ListingResult(ok=True, market="shopify", message="ok", raw={})

        def upload_product(self, payload):
            from src.markets.adapters.base import ListingResult
            captured["payload"] = payload
            return ListingResult(ok=True, market="shopify", external_id="P-1", message="ok", raw={})

    monkeypatch.setattr("src.markets.adapters.shopify.ShopifyAdapter", _FakeAdapter)
    mod.UploadDispatcher().dispatch(product, ["shopify"])
    return captured.get("payload")


def test_shopify_uses_block_html_when_present(monkeypatch):
    product = {
        "url": "https://example.com/i", "title": "우산", "price_original": 10, "currency": "USD",
        "description": "간단한 원문", "sku": "S1",
        "detail_blocks": {"common": [{"type": "text", "content": "블록 상세 본문"}]},
    }
    payload = _dispatch_shopify_capture(monkeypatch, product)
    assert payload is not None
    assert "블록 상세 본문" in payload.description   # → ShopifyAdapter body_html
    assert "간단한 원문" not in payload.description   # 블록이 plain을 이긴다(셀러 명시적 꾸미기)


def test_shopify_falls_back_to_plain_description(monkeypatch):
    product = {
        "url": "https://example.com/i", "title": "우산", "price_original": 10, "currency": "USD",
        "description": "원문 설명 유지", "sku": "S1",
    }
    payload = _dispatch_shopify_capture(monkeypatch, product)
    assert payload is not None
    assert payload.description == "원문 설명 유지"   # 블록 없으면 기존 동작(회귀 0)


def test_woo_generate_description_prefers_seller_body():
    row = {
        "vendor": "PORTER", "title_ko": "탱커", "brand": "PORTER",
        "source_country": "JP", "category": "bag",
        "description": '<p style="x">셀러가 꾸민 상세 본문</p>',
    }
    html = wc._generate_description(row)
    assert "셀러가 꾸민 상세 본문" in html      # 셀러 상세가 본문에 반영
    assert "관부가세" in html                   # 컴플라이언스 안내는 유지
    assert "7-14일" in html                      # 벤더 배송 안내 유지


def test_woo_generate_description_template_when_no_seller_body():
    # 셀러 상세 없으면 기존 템플릿 헤더 폴백(회귀 0) — 기존 테스트와 동일 계약.
    row = {"vendor": "MEMO_PARIS", "title_ko": "아프리칸 레더", "brand": "MEMO_PARIS",
           "source_country": "FR", "category": "perfume"}
    html = wc._generate_description(row)
    assert "아프리칸 레더" in html and "관부가세" in html and "10-18일" in html


def test_woo_prepare_product_data_carries_seller_description():
    row = {"title_ko": "우산", "sku": "W1", "category": "GEN", "description": "블록 상세 본문",
           "source_country": "CN", "brand": ""}
    prod = wc.prepare_product_data(row, 19900)
    assert "블록 상세 본문" in prod["description"]


def test_woo_end_to_end_blocks_reach_description():
    # _payload_for_market(블록→description_html) → to_collected → catalog_row.description → 본문 반영.
    product = {
        "title": "우산", "price": "12000", "currency": "KRW", "sell_price_krw": 19900,
        "detail_blocks": {"common": [{"type": "text", "content": "우드케이스 상세"}]},
    }
    payload, _ = mod.UploadDispatcher._payload_for_market(product, "woocommerce")
    collected = to_collected(payload)
    catalog_row = {"title_ko": "우산", "sku": "W1", "category": "GEN",
                   "description": collected.get("description_html") or "", "source_country": "CN"}
    html = wc._generate_description(catalog_row)
    assert "우드케이스 상세" in html
