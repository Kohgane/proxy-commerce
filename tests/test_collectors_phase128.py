"""tests/test_collectors_phase128.py — Phase 128 수집기 패키지 테스트.

- 디스패처 도메인 감지
- GenericOgCollector (mock HTML)
- CollectorResult 직렬화
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 기본 임포트
# ---------------------------------------------------------------------------

def test_collectors_package_import():
    """수집기 패키지 임포트 성공."""
    from src.seller_console.collectors import collect, detect_collector
    from src.seller_console.collectors.base import CollectorResult
    assert CollectorResult is not None


def test_collector_result_to_dict():
    """CollectorResult.to_dict() JSON 직렬화 가능."""
    from src.seller_console.collectors.base import CollectorResult
    from decimal import Decimal

    result = CollectorResult(
        success=True,
        url="https://example.com/product",
        source="test",
        title="테스트 상품",
        price=Decimal("99.99"),
        currency="USD",
        images=["https://example.com/img.jpg"],
    )
    d = result.to_dict()
    assert d["success"] is True
    assert d["title"] == "테스트 상품"
    assert d["price"] == "99.99"
    assert d["currency"] == "USD"
    assert len(d["images"]) == 1


def test_collector_result_no_price_to_dict():
    """가격 없는 CollectorResult.to_dict()는 price=None."""
    from src.seller_console.collectors.base import CollectorResult
    result = CollectorResult(success=False, url="x", source="y")
    assert result.to_dict()["price"] is None


# ---------------------------------------------------------------------------
# 디스패처 도메인 감지
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url, expected_class_name", [
    ("https://www.amazon.com/dp/B08N5WRWNW", "AmazonCollector"),
    ("https://www.amazon.co.jp/dp/B08N5WRWNW", "AmazonCollector"),
    ("https://item.rakuten.co.jp/shop/item/", "RakutenCollector"),
    ("https://www.aloyoga.com/products/legging", "AloCollector"),
    ("https://shop.lululemon.com/p/align-pant", "LululemonCollector"),
    ("https://lululemon.com/p/product", "LululemonCollector"),
    ("https://www.somestore.com/product", "GenericOgCollector"),
])
def test_dispatcher_domain_detection(url, expected_class_name):
    """각 도메인에 맞는 컬렉터 반환."""
    from src.seller_console.collectors.dispatcher import detect_collector
    collector = detect_collector(url)
    assert type(collector).__name__ == expected_class_name


def test_dispatcher_adds_taobao_warning():
    """타오바오 URL → warning 추가."""
    from src.seller_console.collectors.dispatcher import collect

    with patch("src.seller_console.collectors.generic_og._fetch_html") as mock_fetch:
        mock_fetch.return_value = "<html><head><meta property='og:title' content='T'/></head><body></body></html>"
        result = collect("https://www.taobao.com/item/123.htm")

    assert any("타오바오" in w for w in result.warnings)


def test_collect_empty_url_failure():
    """빈 URL → success=False."""
    from src.seller_console.collectors.dispatcher import collect
    result = collect("")
    assert result.success is False


def test_collect_adds_https_prefix():
    """http 없는 URL도 처리."""
    from src.seller_console.collectors.dispatcher import collect
    with patch("src.seller_console.collectors.generic_og._fetch_html") as mock_fetch:
        mock_fetch.return_value = "<html><head></head><body></body></html>"
        result = collect("example.com/product")
    # 오류 없이 실행되어야 함 (url에 https:// 자동 추가)
    assert result.url.startswith("https://")


# ---------------------------------------------------------------------------
# GenericOgCollector
# ---------------------------------------------------------------------------

_OG_HTML = """
<html>
<head>
  <meta property="og:title" content="OG 테스트 상품"/>
  <meta property="og:description" content="OG 설명"/>
  <meta property="og:image" content="https://example.com/img1.jpg"/>
  <meta property="og:image" content="https://example.com/img2.jpg"/>
  <meta property="product:price:amount" content="29.99"/>
  <meta property="product:price:currency" content="USD"/>
</head>
<body></body>
</html>
"""

_JSON_LD_HTML = """
<html>
<head>
  <script type="application/ld+json">
  {
    "@type": "Product",
    "name": "JSON-LD 상품",
    "description": "LD 설명",
    "sku": "SKU-001",
    "brand": {"@type": "Brand", "name": "TestBrand"},
    "offers": {"@type": "Offer", "price": "59.99", "priceCurrency": "USD"}
  }
  </script>
</head>
<body></body>
</html>
"""


def test_generic_og_parses_og_tags():
    """OG 메타태그에서 기본 정보 파싱."""
    from src.seller_console.collectors.generic_og import GenericOgCollector

    with patch("src.seller_console.collectors.generic_og._fetch_html", return_value=_OG_HTML):
        result = GenericOgCollector().collect("https://example.com/prod")

    assert result.success is True
    assert result.title == "OG 테스트 상품"
    assert result.description == "OG 설명"
    assert len(result.images) >= 1
    assert str(result.price) == "29.99"
    assert result.currency == "USD"
    assert result.source == "generic_og"


def test_generic_og_parses_json_ld():
    """JSON-LD Product schema에서 정보 파싱."""
    from src.seller_console.collectors.generic_og import GenericOgCollector

    with patch("src.seller_console.collectors.generic_og._fetch_html", return_value=_JSON_LD_HTML):
        result = GenericOgCollector().collect("https://example.com/ld-prod")

    assert result.success is True
    assert result.title == "JSON-LD 상품"
    assert result.brand == "TestBrand"
    assert result.sku == "SKU-001"
    assert str(result.price) == "59.99"


def test_generic_og_failure_on_none_html():
    """HTML fetch 실패 시 success=False."""
    from src.seller_console.collectors.generic_og import GenericOgCollector

    with patch("src.seller_console.collectors.generic_og._fetch_html", return_value=None):
        result = GenericOgCollector().collect("https://example.com/fail")

    assert result.success is False
    assert result.error is not None


# ---------------------------------------------------------------------------
# AmazonCollector
# ---------------------------------------------------------------------------

def test_amazon_collector_fallback_to_og(monkeypatch):
    """PA-API 미설정 시 OG 폴백, source='amazon_og'."""
    from src.seller_console.collectors.amazon import AmazonCollector

    monkeypatch.delenv("AMAZON_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AMAZON_SECRET_KEY", raising=False)
    monkeypatch.delenv("AMAZON_PARTNER_TAG", raising=False)

    with patch("src.seller_console.collectors.generic_og._fetch_html", return_value=_OG_HTML):
        result = AmazonCollector().collect("https://www.amazon.com/dp/B09XYZ0001")

    assert result.success is True
    assert result.source == "amazon_og"
    assert any("AMAZON_ACCESS_KEY" in w or "PA-API" in w for w in result.warnings)


def test_amazon_collector_extracts_asin():
    """ASIN 추출."""
    from src.seller_console.collectors.amazon import _extract_asin
    assert _extract_asin("https://www.amazon.com/dp/B09XYZ0001") == "B09XYZ0001"
    assert _extract_asin("https://www.amazon.com/gp/product/B07TESTXX1") == "B07TESTXX1"
    assert _extract_asin("https://www.amazon.com/some-product") is None


def test_amazon_collector_currency_jp_default():
    """amazon.co.jp → currency defaults to JPY when OG has no currency."""
    from src.seller_console.collectors.amazon import AmazonCollector

    # HTML without currency meta
    html_no_currency = "<html><head><meta property='og:title' content='Test'/></head><body></body></html>"

    with patch("src.seller_console.collectors.generic_og._fetch_html", return_value=html_no_currency):
        result = AmazonCollector().collect("https://www.amazon.co.jp/dp/B09XYZ0001")

    assert result.currency == "JPY"


# ---------------------------------------------------------------------------
# RakutenCollector
# ---------------------------------------------------------------------------

def test_rakuten_collector_fallback_to_og(monkeypatch):
    """RAKUTEN_APP_ID 미설정 시 OG 폴백."""
    from src.seller_console.collectors.rakuten import RakutenCollector

    monkeypatch.delenv("RAKUTEN_APP_ID", raising=False)

    with patch("src.seller_console.collectors.generic_og._fetch_html", return_value=_OG_HTML):
        result = RakutenCollector().collect("https://item.rakuten.co.jp/shop/item/")

    assert result.success is True
    assert result.source == "rakuten_og"
    assert any("RAKUTEN_APP_ID" in w for w in result.warnings)
