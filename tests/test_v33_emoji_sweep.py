"""tests/test_v33_emoji_sweep.py — v33 3-4: 전역 이모지 박멸(라인 아이콘셋)."""
from __future__ import annotations

import glob
import re

import pytest

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "✅❌⚠ℹ⭐✨️]"
)

_USER_TEMPLATES = sorted(
    set(glob.glob("src/seller_console/templates/**/*.html", recursive=True))
    | set(glob.glob("src/templates/**/*.html", recursive=True))
)


# v53 STEP4(오너 명시 예외): 북마클릿 '복사' 방식은 크롬이 아이콘을 숨기므로, 기본 북마크 '이름'에
#   ⚡ 접두를 붙여 눈에 띄게 한다(UI 데코 아님 = 사용자가 입력할 북마크 이름). 이 파일에 한해 ⚡ 허용.
_ALLOWED = {"bookmarklet.html": "⚡"}


@pytest.mark.parametrize("path", _USER_TEMPLATES)
def test_user_template_has_no_emoji(path):
    text = open(path, encoding="utf-8").read()
    allow = _ALLOWED.get(path.rsplit("/", 1)[-1])
    if allow:
        text = text.replace(allow, "")
    found = _EMOJI.findall(text)
    assert not found, f"{path}: 이모지 잔존 {found}"


def test_key_chrome_uses_line_icons():
    for p in ("src/seller_console/templates/partials/topnav.html",
              "src/templates/partials/topnav.html",
              "src/templates/errors/404.html"):
        t = open(p, encoding="utf-8").read()
        assert "bi bi-shop" in t            # 셀러 콘솔 → 라인 아이콘
        assert "bi bi-tools" in t           # 관리자
