"""tests/test_v40_landing_design.py — v40 디자인: 다크 히어로 + 다리(현수교) 라인아트 시그니처.

기준 디자인목업_v40.html: 다크 히어로("건너세요. 수집에서 판매까지."), 다리 라인아트(히어로+섹션 디바이더 반복),
한지/먹 교차, 금 CTA 밴드. 토큰 단일소스(하드코딩 hex 0)·시그니처(다리/게이트/키스톤) 살림.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

TPL = Path("src/templates/landing.html").read_text(encoding="utf-8")
CSS = Path("src/static/app.css").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_dark_hero_copy(client):
    html = client.get("/").get_data(as_text=True)
    assert "건너세요" in html and "수집" in html and "판매" in html
    # 다크 히어로 그라데이션(먹 토큰)
    assert "radial-gradient(120% 90% at 50% 0%, var(--ink-2)" in TPL


def test_bridge_lineart_signature_repeated():
    # 다리 라인아트가 매크로로 정의되고 히어로·디바이더에 반복(시그니처)
    assert "macro bridge_art()" in TPL
    assert TPL.count("bridge_art()") >= 2          # 정의 + 히어로 + 디바이더(최소 2회 호출)
    assert 'class="bridge-art"' in TPL and 'class="divider"' in TPL
    # 게이트 아치 원 + 주황 키스톤 점 + 청록 강(다리 구조)
    assert 'circle cx="600" cy="118" r="58"' in TPL          # 게이트 아치
    assert 'circle cx="600" cy="60" r="9" fill="var(--orange)"' in TPL  # 키스톤(주황 점)
    assert 'stroke="var(--teal)"' in TPL                     # 청록 강


def test_gold_cta_band_and_dark_sections():
    assert "class=\"band reveal\"" in TPL
    assert "linear-gradient(135deg, var(--gold-bright)" in TPL   # 금 CTA 밴드
    assert "block dark" in TPL                                   # 다크 5단계 섹션


def test_tokens_single_source_no_hardcoded_hex():
    style = TPL.split("<style>", 1)[1].split("</style>", 1)[0]
    for hexv in ("#1A1714", "#1a1714", "#F5EFE3", "#f5efe3", "#C9A24B", "#c9a24b",
                 "#119A8E", "#119a8e", "#F5821F", "#f5821f", "#D4AF57", "#d4af57", "#EFE7D6", "#efe7d6"):
        assert hexv not in style, f"하드코딩 hex 잔존: {hexv}"
    assert "--gold-bright:" in CSS and "--cream-on-dark:" in CSS   # v40 토큰 app.css 단일소스


def test_no_emoji_no_globe_iconset():
    bad = [c for c in TPL if ord(c) > 0x1F000 or (0x2600 <= ord(c) <= 0x27BF)
           or (0x1F300 <= ord(c) <= 0x1FAFF)]
    assert not bad, f"이모지 잔존: {bad}"
    for b in ("globe", "글러브", "코고가네", "KOHgogane"):
        assert b not in TPL


def test_preserves_hooks_and_real_data(client):
    html = client.get("/").get_data(as_text=True)
    for m in ("쿠팡", "스마트스토어", "Shopify", "Amazon"):
        assert m in html
    assert "For Beginners" in html and "/privacy" in html and "/terms" in html and "/seller/billing" in html
    assert 'href="/auth/login"' in html and "로그인" in html
