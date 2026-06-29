"""tests/test_v39_a2_new_bridge_icon.py — v39 A(개정): 오너 확정 신규 마크로 전량 교체.

흰 배경 + 검정 라운드 보더 + 금 게이트 링 + 주황 키스톤 + 청록 데크. 지구본/글러브 0.
모든 아이콘(파비콘·확장 툴바·PWA·마스터·OG)이 신규 디자인 픽셀(흰 바탕+금/주황/청록)을 포함하는지 검증.
"""
from __future__ import annotations

from pathlib import Path

STATIC = Path("src/seller_console/static")
EXT_ICONS = Path("extensions/chrome-collector/icons")


def _near(px, rgb, tol=40):
    return all(abs(int(px[i]) - rgb[i]) <= tol for i in range(3))


def _has_colors(path, must):
    """이미지가 지정 색군을 모두 포함하는지(허용 오차)."""
    from PIL import Image  # 지연 import — CI(collect-only)는 Pillow 미설치, 로컬서만 픽셀 검증
    im = Image.open(path).convert("RGB")
    im = im.resize((64, 64))
    pixels = list(im.getdata())
    found = {name: False for name in must}
    for p in pixels:
        for name, rgb in must.items():
            if _near(p, rgb):
                found[name] = True
    return found


# 신규 마크 색 — 흰 배경 / 금 #C9A24B / 주황 #F5821F / 청록 #119A8E
WHITE = (255, 255, 255)
GOLD = (201, 162, 75)
ORANGE = (245, 130, 31)
TEAL = (17, 154, 142)


def test_large_icons_white_bg_bridge():
    # 풀 디테일(>=180): 흰 배경 + 금 + 주황 + 청록 전부 존재
    for name in ("icon-512.png", "icon-192.png", "icon-1024.png", "apple-touch-icon.png"):
        f = _has_colors(STATIC / name, {"white": WHITE, "gold": GOLD, "orange": ORANGE, "teal": TEAL})
        assert all(f.values()), f"{name}: {f}"


def test_small_favicons_white_bg_and_accents():
    # 소형 단순(16/32/48): 흰 배경 + 금 + 주황(청록 데크는 소형서 픽셀 적어 금/주황 필수)
    for name in ("favicon-48.png", "favicon-32.png"):
        f = _has_colors(STATIC / name, {"white": WHITE, "gold": GOLD, "orange": ORANGE})
        assert all(f.values()), f"{name}: {f}"


def test_extension_toolbar_icons_white_bg():
    for name in ("128.png", "48.png", "32.png"):
        f = _has_colors(EXT_ICONS / name, {"white": WHITE, "gold": GOLD})
        assert all(f.values()), f"ext {name}: {f}"


def test_master_and_og_white_bg():
    f = _has_colors("assets/brand-icons/icon-master-1024.png",
                    {"white": WHITE, "gold": GOLD, "orange": ORANGE, "teal": TEAL})
    assert all(f.values()), f"master: {f}"


def test_fab_inline_svg_is_new_mark():
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    # 신규 마크: 흰 라운드 배경 rect + 금 게이트 링(circle stroke) + 주황 키스톤 + 청록 데크 2줄
    assert "KGP_BRIDGE_SVG" in cs
    assert 'fill="#ffffff"' in cs and "rx=" in cs                 # 흰 라운드 배경
    assert cs.count('stroke="#119a8e"') >= 2                       # 데크 2줄(청록)
    assert '#f5821f' in cs and "globe" not in cs.lower()           # 주황 키스톤, globe 0
