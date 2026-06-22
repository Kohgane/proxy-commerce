"""tests/test_collect_accuracy_v11.py — v11 P0 수집 정확도 가드.

무관 이미지 제거 + 옵션(색상/사이즈/수량) 보수적 추출을 검증한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collectors.universal_scraper import (  # noqa: E402
    UniversalScraper,
    filter_product_images,
    is_product_image,
)


def test_blacklisted_images_removed():
    junk = [
        "https://img.temu.com/openingemail/flags/kr.png",
        "https://cdn.x.com/supplier-public-tag/v2.png",
        "https://cdn.x.com/ui/arrow.slim.png",
        "https://cdn.x.com/icons/pdf-icon.png",
        "https://cdn.x.com/doc/manual.doc.png",
        "https://t.x.com/1x1.gif",
        "data:image/png;base64,AAAA",
    ]
    for u in junk:
        assert not is_product_image(u), f"무관 이미지가 통과됨: {u}"


def test_product_images_kept_and_deduped():
    imgs = [
        "https://img.temu.com/product/abc_800x800.jpg",
        "https://img.temu.com/product/abc_800x800.jpg",   # 중복
        "https://img.temu.com/material-put/detail1.jpg",
        "https://cdn.x.com/openingemail/flags/kr.png",     # 제거 대상
    ]
    out = filter_product_images(imgs)
    assert out == [
        "https://img.temu.com/product/abc_800x800.jpg",
        "https://img.temu.com/material-put/detail1.jpg",
    ]
    assert out[0].endswith("abc_800x800.jpg")   # 첫 번째 = 대표


def test_parse_html_filters_images_and_extracts_select_options():
    html = """
    <html><head>
      <meta property="og:title" content="테스트 상품">
      <meta property="og:image" content="https://cdn.x.com/product/main.jpg">
      <meta property="product:price:amount" content="19048">
      <meta property="product:price:currency" content="KRW">
    </head><body>
      <img src="https://cdn.x.com/product/main.jpg" width="800" height="800">
      <img src="https://cdn.x.com/openingemail/flags/kr.png" width="20" height="14">
      <img src="https://cdn.x.com/ui/nav_arrow.png" width="12" height="12">
      <label>색상</label>
      <div>
        <button>레드</button><button>블루</button><button>블랙</button>
      </div>
      <select name="사이즈">
        <option>선택하세요</option><option>S</option><option>M</option><option>L</option>
      </select>
    </body></html>
    """
    res = UniversalScraper().parse_html(html, "https://temu.com/g-123.html")
    # 무관 이미지(flags/arrow) 미수집
    assert all("flags" not in i and "arrow" not in i for i in res.images)
    assert any("product/main.jpg" in i for i in res.images)
    # 옵션 추출(색상/사이즈)
    names = {o["name"] for o in res.options}
    assert any("색상" in n for n in names)
    color = next(o for o in res.options if "색상" in o["name"])
    assert "레드" in color["values"] and "블루" in color["values"]


def test_options_empty_when_no_option_groups():
    html = "<html><body><p>옵션 없는 단순 페이지</p></body></html>"
    res = UniversalScraper().parse_html(html, "https://x.com/item")
    assert res.options == []   # 확신 없으면 비움(거짓 데이터 금지)
