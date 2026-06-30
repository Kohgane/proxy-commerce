"""tests/test_v39e2_price.py — v39-E2 #1: 가격 추출 강화(PDP 현재가 우선·취소선/추천 제외).

PDP 컨테이너 스코프에서 현재가(판매가)를 읽는다. 할인전(취소선·정가)·추천/리뷰 영역 가격 제외.
못 읽으면 정직(None) — 임의 환산 금지(호출부가 needs_check).
"""
from __future__ import annotations

import pytest

pytest.importorskip("bs4")

from src.collectors.universal_scraper import UniversalScraper


def _price(html, url="https://temu.com/p"):
    res = UniversalScraper().parse_html(html, url)
    return (str(res.price) if res.price is not None else None, res.currency)


def test_current_price_over_original_strikethrough():
    html = """
    <div class="product-detail">
      <div class="price-box">
        <del class="original-price">$99.00</del>
        <span class="current-price">$59.90</span>
      </div>
    </div>"""
    p, cur = _price(html)
    assert p == "59.90" and cur == "USD"     # 취소선 정가($99) 아닌 판매가($59.90)


def test_excludes_recommend_region_price():
    html = """
    <div class="product-detail">
      <div class="price">$42.00</div>
    </div>
    <div class="recommend">
      <div class="price">$9.99</div>
    </div>"""
    p, _ = _price(html)
    assert p == "42.00"                       # 추천영역 $9.99 아님


def test_itemprop_price_content():
    html = '<div class="product-info"><span itemprop="price" content="123.45">123,45</span></div>'
    p, _ = _price(html)
    assert p == "123.45"


def test_krw_symbol_currency():
    html = '<div class="product-detail"><div class="sale-price">₩ 39,000</div></div>'
    p, cur = _price(html)
    assert p == "39000" and cur == "KRW"


def test_honest_none_when_no_price():
    html = '<div class="product-detail"><h1>상품명만 있음</h1></div>'
    p, _ = _price(html)
    assert p is None                          # 임의 환산/가짜값 0


def test_extension_scoped_price_helper_present():
    from pathlib import Path
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "_kgpScopedPrice" in cs
    assert "_kgpPriceIsOriginal" in cs        # 취소선/정가 제외
    assert "_kgpInNonProd" in cs              # 추천/리뷰 영역 제외
