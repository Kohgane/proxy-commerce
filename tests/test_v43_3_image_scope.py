"""tests/test_v43_3_image_scope.py — v43-3: 이미지 클릭시점 추출 스코프.

가격처럼 이미지도 클릭 시점 DOM에서 읽되, 판매자/브랜드 로고(예 'ALL IN HOME')를 alt/class/조상영역으로
배제하고 갤러리(대표)/상세 2버킷으로 나눈다. 상품 ID 귀속은 서버(행) 저장으로 이미 보장.
"""
from __future__ import annotations

from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_seller_logo_excluded_by_alt_class_ancestor():
    assert "_kgpIsSellerLogo" in CS
    # src뿐 아니라 alt/class/조상(판매자 정보 영역)으로도 로고 배제.
    assert "_kgpSellerLogoRe" in CS
    assert "seller|merchant|store" in CS
    # 루프에서 판매자 로고면 제외.
    assert "_kgpIsSellerLogo(im)" in CS


def test_gallery_detail_two_buckets():
    assert "gallery_images: gallery" in CS
    assert "detail_images: detail" in CS
    assert "_KGP_GALLERY_SEL" in CS and "_KGP_DETAIL_SEL" in CS
    # 대표 이미지는 갤러리 첫 장 우선(로고 배제).
    assert "gallery[0] || images[0] || ogImage" in CS


def test_server_already_binds_images_per_item():
    """서버는 이미 수집 행(상품 ID)에 gallery/detail 이미지를 귀속(누출 0) — 회귀 확인."""
    ext = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert "gallery_images" in ext and "detail_images" in ext
