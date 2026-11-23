"""순찰 122b-U1 → 오너 11-23 「앱이 실제 앱처럼」 개정 — 폰·앱 웹뷰 셸 하나(partials/m_shell.html).

계약(개정): 하단 탭 4개(수집·목록·주문·더보기, 폰만) · 활성 탭 = 지금 화면 · 상단은 얇은 바(뒤로·제목·검색) · PC 탑바·사이드바는
폰에서 안 보인다(「더보기」는 사이드바 시트가 아니라 /seller/m?tab=more 화면) · 드로어(?drawer=1)엔 셸 없음 · 셸 CSS는 토큰만 ·
390px 가로 스크롤 0(Playwright, 브라우저 있을 때만).
"""
from __future__ import annotations

import re

import pytest

from src.order_webhook import app

TABS = (("/seller/m", "수집"), ("/seller/collect/history", "목록"), ("/seller/orders", "주문"), ("/seller/m?tab=more", "더보기"))


def _html(path: str) -> str:
    return app.test_client().get(path).get_data(as_text=True)


def _tabbar(html: str) -> str:
    m = re.search(r'<nav class="kgp-mtab"[^>]*>(.*?)</nav>', html, re.S)
    assert m, "하단 탭바가 없다"
    return m.group(1)


def test_tabbar_has_four_tabs_and_active_follows_page():
    for path, label in TABS:
        bar = _tabbar(_html(path))
        assert bar.count('class="kgp-mtab-item') == 4
        for href, lab in TABS:
            assert f'href="{href}"' in bar and f"<span>{lab}</span>" in bar
        active = re.findall(r'class="kgp-mtab-item active" href="([^"]+)"', bar)
        assert active == [path], (path, active)                     # 활성 탭 = 지금 화면 하나


def test_topbar_is_thin_back_title_search_and_no_hamburger():
    html = _html("/seller/markets")                                   # 탭 루트가 아닌 화면 = 뒤로가 있다
    top = re.search(r'<header class="kgp-mtop".*?</header>', html, re.S).group(0)
    assert 'data-role="m-back"' in top and 'data-role="m-title"' in top and "toggleMobileSearch()" in top
    assert "bi-list" not in top and "toggleSidebar" not in top
    root = re.search(r'<header class="kgp-mtop".*?</header>', _html("/seller/orders"), re.S).group(0)
    assert 'data-role="m-back"' not in root                           # 탭 루트엔 뒤로 없음


def test_drawer_mode_has_no_shell():
    html = app.test_client().get("/seller/collect/history?drawer=1").get_data(as_text=True)
    assert 'class="kgp-mtab"' not in html and 'class="kgp-mtop"' not in html


def test_shell_css_tokens_only_and_desktop_hidden():
    block = open("src/static/m_shell.css", encoding="utf-8").read()
    assert ".kgp-mtop, .kgp-mtab, .kgp-jobline, .kgp-mskel { display: none; }" in block   # 데스크톱 기본 숨김
    assert "@media (max-width: 767.98px)" in block and "html.kgp-app .kgp-mtab" in block
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", block)              # 하드코딩 hex 0 — 토큰만
    assert "env(safe-area-inset-bottom" in block and "env(safe-area-inset-top" in block
    assert "100dvh" in block and "font-size: 16px" in block and "overscroll-behavior-y" in block


def _mobile_drive(path: str, script: str):
    """진짜 브라우저(390×844)에 콘솔 화면을 태운다 — 우리 CSS 셋은 인라인으로 싣고 바깥 자원(CDN)은 끊는다."""
    import tempfile
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from tests._pw import launch_opts
    html = _html(path)
    css = "".join(open(p, encoding="utf-8").read() for p in (      # 오너 11-23: 부트스트랩도(실제 폰과 같게 — 모달 등이 숨는다)
        "src/static/vendor/bootstrap-5.3.3/bootstrap.min.css",
        "src/static/app.css", "src/static/m_shell.css", "src/seller_console/static/seller.css", "src/seller_console/static/console.css"))
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
            b.close()
        return out
    finally:
        Path(fp).unlink(missing_ok=True)


@pytest.mark.skipif(not __import__("tests._pw", fromlist=["chromium_hits"]).chromium_hits(), reason="chromium 미설치(Playwright 브라우저)")
@pytest.mark.parametrize("path", ["/seller/dashboard", "/seller/collect/history", "/seller/orders", "/seller/m", "/seller/m?tab=more"])
def test_mobile_shell_in_browser(path):
    """390px: 가로 스크롤 0 · 탭바 보이고 바닥에 붙음 · 탭 4개 터치 타깃 ≥44 · 얇은 상단 바 · PC 탑바·사이드바 안 보임."""
    out = _mobile_drive(path, """() => {
      const de = document.documentElement;
      const bar = document.querySelector('.kgp-mtab');
      const r = bar.getBoundingClientRect();
      const tabs = [...bar.querySelectorAll('.kgp-mtab-item')].map(t => t.getBoundingClientRect().height);
      const top = document.querySelector('.kgp-mtop').getBoundingClientRect();
      const vis = (sel) => { const e = document.querySelector(sel); if (!e) return false;
        const b = e.getBoundingClientRect(); const cs = getComputedStyle(e);
        return cs.display !== 'none' && cs.visibility !== 'hidden' && b.width > 0 && b.height > 0 && b.top < innerHeight && b.bottom > 0 && b.left < innerWidth && b.right > 0; };
      return {sw: de.scrollWidth, cw: de.clientWidth, barDisplay: getComputedStyle(bar).display,
              barBottom: Math.round(r.bottom), vh: window.innerHeight, tabs, topH: Math.round(top.height), topY: Math.round(top.top),
              pcTop: vis('.console-topbar'), sidebar: vis('#sidebarDrawer'), oldBar: !!document.querySelector('.kgp-tabbar, .mobile-topbar, .m-tabbar')};
    }""")
    assert out["sw"] == out["cw"] == 390, out
    assert out["barDisplay"] == "flex" and out["barBottom"] == out["vh"], out
    assert len(out["tabs"]) == 4 and min(out["tabs"]) >= 44, out
    assert out["topY"] == 0 and 44 <= out["topH"] <= 64, out
    assert out["pcTop"] is False and out["sidebar"] is False and out["oldBar"] is False, out
