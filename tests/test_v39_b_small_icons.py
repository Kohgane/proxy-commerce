"""tests/test_v39_b_small_icons.py — v39 B: 소형 전용 고대비 아이콘(16/32/48) 검증."""
from __future__ import annotations

from pathlib import Path

import pytest

STATIC = Path("src/seller_console/static")


def _has_color(img_path, target, tol=40):
    from PIL import Image
    im = Image.open(img_path).convert("RGBA")
    tr, tg, tb = target
    for r, g, b, a in im.getdata():
        if a > 80 and abs(r - tr) <= tol and abs(g - tg) <= tol and abs(b - tb) <= tol:
            return True
    return False


def test_small_icons_exist():
    for sz in (16, 32, 48):
        assert (STATIC / f"favicon-{sz}.png").exists(), f"favicon-{sz}.png 누락"
    assert (STATIC / "favicon.ico").exists()


def test_16px_is_high_contrast_not_mushed():
    # 16px에 청록 아치(#119A8E) + 주황 키스톤(#F5821F)이 실제로 살아있어야(뭉개짐 0)
    p = STATIC / "favicon-16.png"
    assert _has_color(p, (17, 154, 142)), "16px에 청록 아치 없음(뭉개짐)"
    assert _has_color(p, (245, 130, 31)), "16px에 주황 키스톤 없음(뭉개짐)"


def test_32px_high_contrast():
    p = STATIC / "favicon-32.png"
    assert _has_color(p, (17, 154, 142)) and _has_color(p, (245, 130, 31))


def test_favicon_cache_bumped_to_178():
    base = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    assert "v='178'" in base and "v='177'" not in base
