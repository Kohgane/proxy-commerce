"""tests/test_v29_landing_redesign.py — v29 PART2: 랜딩 전면 재설계(Apple식 스크롤 내러티브) 가드."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

TPL = Path("src/templates/landing.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_landing_has_no_emoji():
    bad = [c for c in TPL if ord(c) > 0x1F000 or (0x2600 <= ord(c) <= 0x27BF)
           or (0x1F300 <= ord(c) <= 0x1FAFF)]
    assert not bad, f"랜딩에 이모지 잔존: {bad}"


def test_landing_scroll_narrative_sections(client):
    html = client.get("/").get_data(as_text=True)
    # v39-D 에디토리얼 섹션: 3-피처·5단계·인페이지 편집·요금·법적 링크
    for needle in ("One Bridge, Every Market", "5 Steps", "In-page Editing",
                   "Pricing", "개인정보처리방침", "이용약관"):
        assert needle in html, f"섹션/링크 {needle} 누락"
    # 슬림 글래스 내비 + 등장 리빌 + reduced-motion 존중
    assert 'class="lpnav"' in TPL and "backdrop-filter: saturate" in TPL
    assert "IntersectionObserver" in TPL
    assert "prefers-reduced-motion" in TPL
    # 콘솔 미리보기 샷(평면 금지 — 제품이 곧 데모)
    assert 'class="shot ' in TPL


def test_landing_social_proof_real_no_fake_numbers(client):
    html = client.get("/").get_data(as_text=True)
    # 지원 마켓(실데이터) 노출
    for m in ("쿠팡", "스마트스토어", "Shopify", "Amazon"):
        assert m in html
    # 가짜 셀러/수집 수치 날조 금지(예: "1,234명 셀러", "10,000+ 수집")
    assert not re.search(r"[\d,]{2,}\s*명", html), "가짜 셀러 수 노출"
    assert not re.search(r"[\d,]{3,}\s*\+?\s*(셀러|수집|상품 등록)", html), "가짜 수치 노출"


def test_landing_core_ctas_present(client):
    html = client.get("/").get_data(as_text=True)
    assert "무료로 시작" in html              # 무료 시작 퍼널
    assert "For Beginners" in html             # 초보 온보딩 진입
    assert "/seller/start" in html
    assert "/seller/billing" in html           # 요금제(가짜 혜택 없이 안내)


def test_landing_tokens_single_source_no_hardcoded_brand_hex():
    # 스코프 스타일이 토큰(var(--*)) 사용 — 브랜드 hex 하드코딩 최소화
    assert "var(--ink" in TPL and "var(--gold" in TPL and "var(--teal" in TPL
    # 옛 글러브/지구본/구브랜드 0
    for bad in ("글러브", "globe", "코고가네", "KOHgogane"):
        assert bad not in TPL
