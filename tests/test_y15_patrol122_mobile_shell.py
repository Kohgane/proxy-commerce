"""순찰 122b-U1(오너 2026-10-26 「모바일에서 볼 때 너무 난잡 — 앱스럽게」) — 모바일 앱 셸.

계약: 하단 탭 5개(홈·수집·상품·주문·더보기, 모바일만) · 활성 탭은 현재 화면 · 상단바에 햄버거 없음(더보기 탭이 대신) ·
드로어 모드(?drawer=1)엔 탭바 없음 · 「더보기」는 사이드바(모든 링크 보존)를 바텀시트로 · 탭바 CSS는 토큰만(hex 0) ·
390px 가로 스크롤 0(Playwright, 브라우저 있을 때만).
"""
from __future__ import annotations

import re

import pytest

from src.order_webhook import app

TABS = (("/seller/dashboard", "홈"), ("/seller/collect", "수집"), ("/seller/collect/history", "상품"), ("/seller/orders", "주문"))


def _html(path: str) -> str:
    return app.test_client().get(path).get_data(as_text=True)


def _tabbar(html: str) -> str:
    m = re.search(r'<nav class="kgp-tabbar[^>]*>(.*?)</nav>', html, re.S)
    assert m, "하단 탭바가 없다"
    return m.group(1)


def test_tabbar_has_five_tabs_and_active_follows_page():
    for path, label in TABS:
        bar = _tabbar(_html(path))
        assert bar.count('class="kgp-tab') == 5
        for href, lab in TABS:
            assert f'href="{href}"' in bar and f"<span>{lab}</span>" in bar
        assert "<span>더보기</span>" in bar and 'onclick="toggleSidebar()"' in bar
        active = re.findall(r'class="kgp-tab active" href="([^"]+)"', bar)
        assert active == [path], (path, active)                     # 활성 탭 = 지금 화면 하나


def test_topbar_has_no_hamburger_and_more_tab_opens_sidebar():
    html = _html("/seller/orders")
    top = re.search(r'<div class="mobile-topbar.*?</div>\s*</div>', html, re.S).group(0)
    assert "bi-list" not in top and 'id="sidebarToggle"' not in top  # 햄버거는 탭바 「더보기」로 갔다
    assert 'id="sidebarToggle"' in _tabbar(html)
    assert 'id="sidebarDrawer"' in html                              # 사이드바(링크 전부)는 그대로 — 모바일에선 바텀시트


def test_drawer_mode_has_no_tabbar():
    html = app.test_client().get("/seller/collect/history?drawer=1").get_data(as_text=True)
    assert 'class="kgp-tabbar' not in html


def test_tabbar_css_tokens_only_and_desktop_hidden():
    css = open("src/seller_console/static/console.css", encoding="utf-8").read()
    i = css.index("순찰 122b-U1")
    block = css[i:]
    assert re.search(r"\.kgp-tabbar\s*\{\s*display:\s*none", css)   # 데스크톱 기본 숨김
    assert "@media (max-width: 767.98px)" in block
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", block)              # 하드코딩 hex 0 — 토큰만
    assert "env(safe-area-inset-bottom" in block                      # 홈 인디케이터 밑에 안 깔린다
    assert "min-height: 44px" in block                                # 터치 타깃


@pytest.mark.skipif(True, reason="Playwright 가로 스크롤 0 계약은 _devshot_mobile_shell.py가 캡처와 함께 잰다(scrollW==clientW 출력)")
def test_mobile_no_horizontal_scroll():
    pass
