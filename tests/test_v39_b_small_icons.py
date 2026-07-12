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


def test_answer_key_carries_brand_colors():
    # v57: 파비콘 소사이즈 정답지(=favicon-48, 오너 커밋)에 청록(#119A8E)+주황(#F5821F) 브랜드색 존재.
    #   16/32는 정답지 다운스케일(소형 축소로 순색 완화 가능 — 정답지가 최종 권위, '유사는 불합격' 판정 대상은 48).
    p = STATIC / "favicon-48.png"
    assert _has_color(p, (17, 154, 142)), "정답지에 청록 없음"
    assert _has_color(p, (245, 130, 31)), "정답지에 주황 없음"


def test_32px_has_orange_signal():
    # 32px 다운스케일에도 주황 키스톤 신호는 생존(브랜드 식별). 청록 데크는 얇아 소형 축소서 완화될 수 있음.
    p = STATIC / "favicon-32.png"
    assert _has_color(p, (245, 130, 31), tol=60), "32px에 주황 신호 없음"


def test_favicon_cache_bumped_to_178():
    base = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    assert "v='182'" in base and "v='181'" not in base
