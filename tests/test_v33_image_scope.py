"""tests/test_v33_image_scope.py — v33 2-1: 이미지 PDP 컨테이너 스코프 한정(엉뚱 이미지 0)."""
from __future__ import annotations

from src.collectors.universal_scraper import _collect_dom_images, _find_product_scope
from bs4 import BeautifulSoup


def _soup(html: str):
    return BeautifulSoup(html, "html.parser")


def test_scopes_to_product_container_and_excludes_recommend_and_review():
    html = """
    <html><body>
      <div class="product-detail">
        <img src="https://cdn.shop.com/main-1.jpg">
        <img src="https://cdn.shop.com/detail-2.jpg">
        <img src="https://cdn.shop.com/detail-3.jpg">
      </div>
      <section class="recommend">
        <img src="https://cdn.shop.com/other-product-a.jpg">
        <img src="https://cdn.shop.com/other-product-b.jpg">
      </section>
      <section class="review-list">
        <img src="https://cdn.shop.com/review-thumb-1.jpg">
      </section>
      <footer><img src="https://cdn.shop.com/footer-banner.jpg"></footer>
    </body></html>
    """
    imgs = _collect_dom_images(_soup(html), "https://shop.com/p/1")
    assert any("main-1" in u for u in imgs)
    assert any("detail-2" in u for u in imgs)
    # 추천/리뷰/푸터 이미지는 0
    assert not any("other-product" in u for u in imgs)
    assert not any("review-thumb" in u for u in imgs)
    assert not any("footer-banner" in u for u in imgs)


def test_falls_back_to_whole_page_when_no_clear_container():
    # 명확한 PDP 컨테이너가 없으면 기존 동작(전체 페이지-제외) 유지(회귀 0)
    html = """
    <html><body>
      <img src="https://cdn.shop.com/a.jpg">
      <img src="https://cdn.shop.com/b.jpg">
      <div class="related"><img src="https://cdn.shop.com/other.jpg"></div>
    </body></html>
    """
    imgs = _collect_dom_images(_soup(html), "https://shop.com/p/1")
    assert any("a.jpg" in u for u in imgs) and any("b.jpg" in u for u in imgs)
    assert not any("other.jpg" in u for u in imgs)   # related 영역 제외 유지


def test_product_scope_requires_multiple_images_conservative():
    # 컨테이너에 이미지 1장뿐이면 스코프로 채택하지 않음(recall 보존)
    html = '<div class="product-info"><img src="https://x.com/one.jpg"></div><img src="https://x.com/two.jpg">'
    scope = _find_product_scope(_soup(html))
    # 전체(soup)로 폴백 → two.jpg도 보임
    imgs = _collect_dom_images(_soup(html), "https://x.com/p")
    assert any("two.jpg" in u for u in imgs)
