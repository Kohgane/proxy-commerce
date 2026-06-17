"""tests/test_scraper_images.py — 상품 이미지 전체 수집(로고/배너 제외, lazy/srcset)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_HTML = """<html><head>
<meta property="og:title" content="가죽 가방">
<meta property="og:image" content="https://cdn.example.com/main.jpg">
</head><body>
<img src="https://cdn.example.com/logo.png">
<img src="https://cdn.example.com/p1_800x800.jpg" width="800" height="800">
<img data-src="https://cdn.example.com/p2.jpg">
<img srcset="https://cdn.example.com/p3_320.jpg 320w, https://cdn.example.com/p3_1200.jpg 1200w">
<img src="https://cdn.example.com/icon-cart.svg">
<img src="https://cdn.example.com/banner_top.jpg">
</body></html>"""


def test_parse_html_collects_all_product_images_excluding_logo_banner():
    from src.collectors.universal_scraper import UniversalScraper
    sp = UniversalScraper().parse_html(_HTML, "https://example.com/p/1")
    imgs = sp.images
    # og 대표 + 갤러리 이미지들이 모두 포함
    assert "https://cdn.example.com/main.jpg" in imgs
    assert "https://cdn.example.com/p1_800x800.jpg" in imgs
    assert "https://cdn.example.com/p2.jpg" in imgs          # data-src(lazy)
    assert "https://cdn.example.com/p3_1200.jpg" in imgs     # srcset 최대해상도
    # 로고/아이콘/배너는 제외
    assert "https://cdn.example.com/logo.png" not in imgs
    assert "https://cdn.example.com/icon-cart.svg" not in imgs
    assert "https://cdn.example.com/banner_top.jpg" not in imgs
    assert len(imgs) >= 4


def test_collect_dom_images_dedupes_and_resolves_relative():
    from src.collectors.universal_scraper import _collect_dom_images
    from bs4 import BeautifulSoup
    html = '<div><img src="/a.jpg"><img src="/a.jpg"><img src="//cdn.x/b.jpg"></div>'
    soup = BeautifulSoup(html, "html.parser")
    imgs = _collect_dom_images(soup, "https://shop.example/p")
    assert imgs == ["https://shop.example/a.jpg", "https://cdn.x/b.jpg"]
