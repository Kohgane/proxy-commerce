"""tests/test_v39d_landing_design.py — v39-D 디자인 시스템: 랜딩을 디자인목업_v39와 1:1로.

"디지털 한지 위의 금속활자" — 밝은 한지 위 대형 세리프 + 네오클래식 에디토리얼.
토큰 단일소스(app.css, 하드코딩 hex 금지) · 이모지 0(bi-* 단일 아이콘셋) · 실데이터(가짜 후기/수치 0).
"""
from __future__ import annotations

import os
import re
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


def test_mockup_structure_present(client):
    html = client.get("/").get_data(as_text=True)
    # 목업 핵심 섹션/카피
    for needle in ("건너세요", "수집", "판매", "막막함은 우리가", "수익은 사장님이",
                   "디지털 한지 위의 금속활자", "One Bridge, Every Market", "5 Steps", "In-page Editing"):
        assert needle in html, f"목업 섹션 누락: {needle}"


def test_console_shot_and_pipeline(client):
    html = client.get("/").get_data(as_text=True)
    # 콘솔 미리보기 샷(브라우저 크롬 바 + 사이드 + KPI + 행)
    assert 'class="shot ' in html and 'class="shot-bar"' in html
    assert 'class="kpis"' in html and 'class="prow"' in html
    # 5단계 파이프라인
    assert 'class="steps5"' in html
    for n in ("01", "02", "03", "04", "05"):
        assert f'>{n}<' in html


def test_no_emoji_uses_bi_iconset():
    bad = [c for c in TPL if ord(c) > 0x1F000 or (0x2600 <= ord(c) <= 0x27BF)
           or (0x1F300 <= ord(c) <= 0x1FAFF)]
    assert not bad, f"랜딩 이모지 잔존: {bad}"
    assert "bi bi-" in TPL                      # 단일 아이콘셋


def test_tokens_single_source_no_hardcoded_brand_hex():
    # 스코프 CSS는 토큰(var(--*))만 — 브랜드 hex 리터럴 0
    style = TPL.split("<style>", 1)[1].split("</style>", 1)[0]
    for hexv in ("#1A1714", "#1a1714", "#F5EFE3", "#f5efe3", "#C9A24B", "#c9a24b",
                 "#119A8E", "#119a8e", "#F5821F", "#f5821f", "#FBF8F1", "#fbf8f1"):
        assert hexv not in style, f"하드코딩 브랜드 hex 잔존: {hexv}"
    assert "var(--ink" in style and "var(--gold" in style and "var(--teal" in style and "var(--paper" in style
    # 신규 토큰이 app.css 단일소스에 정의됨
    assert "--paper:" in CSS and "--teal-bright:" in CSS and "--radius-xl:" in CSS


def test_real_data_no_fake_reviews_or_numbers(client):
    html = client.get("/").get_data(as_text=True)
    # 지원 마켓(실데이터) 노출
    for m in ("쿠팡", "스마트스토어", "Shopify", "Amazon"):
        assert m in html
    # 가짜 셀러 수·후기 수치 날조 금지
    assert not re.search(r"[\d,]{2,}\s*명", html), "가짜 셀러 수"
    assert not re.search(r"[\d,]{3,}\s*\+?\s*(셀러|후기|리뷰)", html), "가짜 수치"


def test_preserves_required_hooks(client):
    html = client.get("/").get_data(as_text=True)
    assert "For Beginners" in html and "/seller/start" in html
    assert "/privacy" in html and "/terms" in html
    assert "/seller/billing" in html
    # 옛 글러브/지구본/구브랜드 0
    for bad in ("글러브", "globe", "코고가네", "KOHgogane"):
        assert bad not in TPL
