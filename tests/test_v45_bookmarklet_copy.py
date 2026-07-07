"""tests/test_v45_bookmarklet_copy.py — 북마클릿 코드조각 1.5배 + 클릭 복사(복사됨 토스트 1회)."""
from __future__ import annotations

from pathlib import Path

BM = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")


def test_copy_chip_markup():
    # chrome://bookmarks가 클릭 복사 칩으로(코드 텍스트 → 복사 가능)
    assert "kgp-copy-code" in BM
    assert 'data-copy="chrome://bookmarks"' in BM


def test_copy_chip_font_1_5x():
    # 폰트 1.5배(small≈0.875rem → ~1.35rem)
    assert "font-size: 1.35rem" in BM


def test_copy_handler_and_toast_once():
    assert "navigator.clipboard" in BM and "execCommand('copy')" in BM   # 복사 + 폴백
    assert "복사됐어요" in BM                                            # 복사됨 토스트
    assert "_kgpCopied" in BM                                            # 중복 토스트 방지(1회)
    assert "closest('.kgp-copy-code')" in BM                             # 델리게이트(다른 코드조각도 동일 패턴)
