"""tests/test_v39e2_image_buckets.py — v39-E2 #2: 썸네일(갤러리) ↔ 본문(상세) 이미지 분리.

갤러리(PDP 상단 캐러셀/썸네일)와 상세설명 영역 이미지를 두 버킷으로 분리.
로고/배너/추천 영역 이미지 제외, 중복은 갤러리 우선(대표). 못 찾으면 빈 리스트(가짜 0).
"""
from __future__ import annotations

import pytest

pytest.importorskip("bs4")

from src.collectors.universal_scraper import collect_image_buckets

_HTML = """
<html><body>
  <div class="product-gallery">
    <img src="https://cdn.x.com/main1.jpg">
    <img data-src="https://cdn.x.com/main2.jpg">
    <img src="https://cdn.x.com/logo.png">           <!-- 제외(로고) -->
  </div>
  <div class="product-description">
    <p>상세 설명</p>
    <img src="https://cdn.x.com/detail-spec1.jpg">
    <img src="https://cdn.x.com/detail-size2.jpg">
  </div>
  <div class="recommend">
    <img src="https://cdn.x.com/other-product.jpg">  <!-- 제외(추천) -->
  </div>
</body></html>
"""


def test_buckets_split_gallery_and_detail():
    b = collect_image_buckets(_HTML, "https://x.com/p")
    assert "https://cdn.x.com/main1.jpg" in b["gallery"]
    assert "https://cdn.x.com/main2.jpg" in b["gallery"]
    assert "https://cdn.x.com/detail-spec1.jpg" in b["detail"]
    assert "https://cdn.x.com/detail-size2.jpg" in b["detail"]


def test_buckets_exclude_logo_and_recommend():
    b = collect_image_buckets(_HTML, "https://x.com/p")
    joined = b["gallery"] + b["detail"]
    assert not any("logo" in u for u in joined)          # 로고 제외
    assert not any("other-product" in u for u in joined)  # 추천상품 제외


def test_buckets_no_overlap_gallery_first():
    # 갤러리에도 상세에도 같은 url이 있으면 갤러리(대표)에만(중복 0)
    html = """<div class="product-gallery"><img src="https://x/a.jpg"></div>
              <div class="description"><img src="https://x/a.jpg"><img src="https://x/b.jpg"></div>"""
    b = collect_image_buckets(html, "https://x.com/p")
    assert "https://x/a.jpg" in b["gallery"]
    assert "https://x/a.jpg" not in b["detail"]           # 갤러리 우선, 상세 중복 제거
    assert "https://x/b.jpg" in b["detail"]


def test_empty_when_no_buckets_honest():
    b = collect_image_buckets("<html><body><p>no images</p></body></html>", "https://x.com/p")
    assert b == {"gallery": [], "detail": []}             # 가짜 생성 0


def test_parse_html_populates_raw_meta_buckets():
    from src.collectors.universal_scraper import UniversalScraper
    res = UniversalScraper().parse_html(_HTML, "https://x.com/p")
    assert res.raw_meta.get("gallery_images")             # 갤러리 버킷 채워짐
    assert res.raw_meta.get("detail_images")              # 상세 버킷 채워짐
    assert "https://cdn.x.com/detail-spec1.jpg" in res.raw_meta["detail_images"]


def test_drawer_template_has_separate_sections():
    from pathlib import Path
    tpl = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "detailImagesBlock" in tpl and "detailGallery" in tpl
    assert "상세설명 이미지" in tpl
    assert "renderDetailGallery" in tpl
