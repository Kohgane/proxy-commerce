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


def _mobile_drive(path: str, script: str):
    """진짜 브라우저(390×844)에 콘솔 화면을 태운다 — 우리 CSS 셋은 인라인으로 싣고 바깥 자원(CDN)은 끊는다."""
    import tempfile
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from tests._pw import launch_opts
    html = _html(path)
    css = "".join(open(p, encoding="utf-8").read() for p in (
        "src/static/app.css", "src/seller_console/static/seller.css", "src/seller_console/static/console.css"))
    html = html.replace("</head>", f"<style>{css}</style></head>", 1)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        fp = f.name
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(**launch_opts())
            ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            page = ctx.new_page()
            page.route("**/*", lambda r: r.abort() if r.request.url.startswith("http") else r.continue_())
            page.goto("file://" + fp, wait_until="domcontentloaded")
            page.wait_for_timeout(300)
            out = page.evaluate(script)
            if isinstance(out, dict) and out.get("_toggle"):
                page.evaluate("toggleSidebar()")
                page.wait_for_timeout(500)                      # 바텀시트 전환(.28s)이 끝난 뒤 잰다
                out["after"] = page.evaluate("document.getElementById('sidebarDrawer').getBoundingClientRect().top")
            b.close()
        return out
    finally:
        Path(fp).unlink(missing_ok=True)


@pytest.mark.skipif(not __import__("tests._pw", fromlist=["chromium_hits"]).chromium_hits(), reason="chromium 미설치(Playwright 브라우저)")
@pytest.mark.parametrize("path", ["/seller/dashboard", "/seller/collect/history", "/seller/orders"])
def test_mobile_shell_in_browser(path):
    """390px: 가로 스크롤 0 · 탭바 보이고 바닥에 붙음 · 탭 5개 터치 타깃 ≥44 · 사이드바는 닫혀 있고(화면 밖) 「더보기」로 열린다."""
    out = _mobile_drive(path, """() => {
      const de = document.documentElement;
      const bar = document.querySelector('.kgp-tabbar');
      const r = bar.getBoundingClientRect();
      const tabs = [...bar.querySelectorAll('.kgp-tab')].map(t => t.getBoundingClientRect().height);
      const sb = document.getElementById('sidebarDrawer');
      const before = sb.getBoundingClientRect().top;
      return {_toggle: true, sw: de.scrollWidth, cw: de.clientWidth, barDisplay: getComputedStyle(bar).display,
              barBottom: Math.round(r.bottom), vh: window.innerHeight, tabs, before,
              hamburger: !!document.querySelector('.mobile-topbar #sidebarToggle')};
    }""")
    assert out["sw"] == out["cw"] == 390, out
    assert out["barDisplay"] == "grid" and out["barBottom"] == out["vh"], out
    assert len(out["tabs"]) == 5 and min(out["tabs"]) >= 44, out
    assert out["before"] >= out["vh"] and out["after"] < out["vh"], out     # 닫힘=화면 아래, 더보기=올라온다
    assert out["hamburger"] is False
