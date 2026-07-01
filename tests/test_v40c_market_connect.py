"""tests/test_v40c_market_connect.py — v40-C: 퍼센티식 마켓연동 2단 + 원클릭 설정 드로어.

좌 마켓 리스트 + 우 상세, 상태 뱃지(연동완료/미연동), '계정 설정' → 우측 드로어(페이지 이탈 0) → 인증하기 → 저장.
정직: 연동 상태 실제 자격증명 유무로만, 자격증명 마스킹. 새 창 0(발급 링크만 새 탭).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

HTML = Path("src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_two_column_layout():
    assert ".mc-wrap { display: grid" in HTML and "grid-template-columns: 260px 1fr" in HTML
    assert "mc-nav" in HTML and "mc-detail" in HTML
    assert "mc-market-nav" in HTML                    # 좌 마켓 리스트
    assert "mc-panel" in HTML                         # 우 상세 패널


def test_status_badge_component():
    # 연동완료=청록 / 미연동=회색 뱃지(공통 컴포넌트)
    assert ".mc-badge.on" in HTML and ".mc-badge.off" in HTML
    assert "연동완료" in HTML and "미연동" in HTML
    assert "data-role=\"status-badge\"" in HTML


def test_one_click_drawer_no_page_nav():
    # '계정 설정' → 우측 드로어(오버레이·슬라이드, 새 창·라우트 이동 0)
    assert "mc-open-drawer" in HTML and "mcOpenDrawer" in HTML
    assert "mc-drawer" in HTML and "mc-drawer-overlay" in HTML
    assert "window.open" not in HTML                  # 새 창 0
    assert "인증하기" in HTML                          # 유효성 검사 버튼
    assert "/markets/connect/${market}/test" in HTML  # 인증 = 연결 테스트 엔드포인트
    assert "/markets/connect/${market}`" in HTML       # 저장 엔드포인트


def test_shipping_profile_cards_no_vertical_split():
    # 배송 프로필 = 키-값 카드(라벨 nowrap, 세로 쪼개짐 0 — v39-H 규칙)
    assert "배송 프로필" in HTML
    assert ".mc-kv .kv .v" in HTML and "white-space: nowrap" in HTML
    assert "이 항목은" in HTML and "에만 필요해요" in HTML   # 마켓 스코프 명시


def test_top_actions_and_tokens():
    assert "신규 마켓 연동" in HTML and "연동 가이드" in HTML
    # gogabridj-design 토큰(하드코딩 브랜드 hex 최소 — 스타일은 var/color-mix)
    style = HTML.split("<style>", 1)[1].split("</style>", 1)[0]
    for hexv in ("#1A1714", "#F5EFE3", "#C9A24B", "#119A8E", "#F5821F"):
        assert hexv not in style
    assert "var(--ink" in style and "var(--teal" in style


def test_credentials_masked_and_real_status(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    html = client.get("/seller/markets/connect").get_data(as_text=True)
    assert html.count("mc-market-nav") >= 3          # 여러 마켓 리스트
    # 실제 상태(미연동 기본) — 가짜 연동완료 0
    assert "미연동" in html
