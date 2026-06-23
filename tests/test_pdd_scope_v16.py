"""tests/test_pdd_scope_v16.py — v16 후속: PDD 스코프(추천/연관 영역 이미지 혼입 방지)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_excludes_recommendation_region_images():
    from src.collectors.universal_scraper import UniversalScraper
    html = """<html><body>
      <div class="product-detail">
        <h1>Cotton Tee</h1>
        <img src="https://img.x.com/main-product.jpg" width="600" height="600">
        <img src="https://img.x.com/detail-2.jpg" width="600" height="600">
      </div>
      <section class="recommendations">
        <img src="https://img.x.com/other-A.jpg" width="400" height="400">
      </section>
      <div class="also-bought"><img src="https://img.x.com/also.jpg" width="400" height="400"></div>
      <footer class="site-footer"><img src="https://img.x.com/footer.jpg" width="400" height="400"></footer>
    </body></html>"""
    imgs = UniversalScraper().parse_html(html, "https://shop.example/p/1").images
    assert "https://img.x.com/main-product.jpg" in imgs
    assert "https://img.x.com/detail-2.jpg" in imgs
    # 추천/함께 본/푸터 영역의 '다른 상품' 이미지는 혼입되지 않아야 함
    for bad in ("other-A", "also.jpg", "footer.jpg"):
        assert not any(bad in u for u in imgs), f"{bad} 혼입됨"


def test_region_helper_direct():
    from bs4 import BeautifulSoup
    from src.collectors.universal_scraper import _in_non_product_region
    soup = BeautifulSoup(
        '<div class="related-products"><img id="a"></div><div class="gallery"><img id="b"></div>',
        "html.parser")
    assert _in_non_product_region(soup.find("img", id="a")) is True
    assert _in_non_product_region(soup.find("img", id="b")) is False


def test_extension_has_region_guard():
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "_kgpInNonProductRegion" in cs and "_kgpNonProductRe" in cs
