"""tests/test_v72_button_isolation.py — v72 STEP4: 버튼 스펙 격리(사이트 CSS 상속 오염 차단).

증상: 알리에서 버튼 과대(사이트 상속 오염). 수리: 중앙 벌크바·우측 단건 FAB·호버 버튼 전부 all:initial
리셋(shadow DOM 동급 격리)+고정 px !important → 사이트 상속/규칙 무력화. 알리·테무·아마존 픽셀 동일.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
import json
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.91"


def test_source_contract_reset_applied_all_buttons():
    assert 'const _KGP_RESET = "all:initial !important;box-sizing:border-box !important;"' in CS
    # 4곳 전부 _KGP_RESET 적용: 카드배지·호버알약·단건 FAB·벌크바.
    assert "return _KGP_RESET + [" in CS                    # kgpCardBadgeStyle/kgpQuickBtnStyle
    assert CS.count("return _KGP_RESET + [") >= 2
    assert "btn.style.cssText = _KGP_RESET + [" in CS       # 단건 FAB
    assert "bar.style.cssText = _KGP_RESET + [" in CS       # 벌크바
    assert "const btnBase = _KGP_RESET +" in CS             # 벌크바 내부 버튼


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


_CHROME_STUB = """
window.chrome = {
  runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u, lastError: null },
  storage: {
    local: { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } },
    sync:  { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } }
  }
};
"""

# 적대적 사이트 CSS — 상속 오염(알리식): html/body에 큰 폰트·라인높이·자간을 !important로 강제.
#   우리 버튼은 documentElement 직속이라 html의 상속을 받는다 → all:initial이 리셋해야 우리 스펙 유지.
#   (자식 스팬도 리셋된 버튼에서 상속받아 정상 — inherited pollution은 all:initial로 완전 차단.)
_HOSTILE = ("<style>html,body{font-size:64px !important;line-height:4 !important;letter-spacing:8px !important;}</style>")


def _cards_html():
    c = ""
    for i in range(1, 6):
        c += ('<div class="card"><a href="/goods/%d"><img width="200" height="200" src="https://img.kwcdn.com/c%d.jpg"></a>'
              '<div class="title">상품 %d</div><div class="price">₩11,235</div></div>' % (i, i, i))
    return c


# [사이트 host | 대표 목록 URL] — 알리·테무·아마존 3사이트.
SITES = [
    ("aliexpress", "https://www.aliexpress.com/w/wholesale-desk.html"),
    ("temu",       "https://www.temu.com/search_result.html?q=desk"),
    ("amazon",     "https://www.amazon.com/s?k=desk"),
]


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
@pytest.mark.parametrize("site,url", SITES, ids=[s[0] for s in SITES])
def test_bulk_bar_font_isolated_from_hostile_css(site, url):
    """3사이트 모두 적대적 CSS(64px) 하에서 벌크바 폰트 = 우리 스펙 16px(사이트 상속 오염 무력)."""
    from playwright.sync_api import sync_playwright

    html = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">' + _HOSTILE +
            '</head><body><div class="grid">' + _cards_html() + '</div></body></html>')
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()
        page.add_init_script(_CHROME_STUB)

        def handler(route):
            if route.request.url.split("#")[0] == url:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(url, wait_until="domcontentloaded")
        page.evaluate("(cs)=>{ (0,eval)(cs); }", CS)
        page.wait_for_timeout(700)
        info = page.evaluate("""() => {
            const bar = document.getElementById('kgp-listing-toolbar');
            if (!bar) return { bar: false };
            const cs = getComputedStyle(bar);
            return { bar: true, fontSize: cs.fontSize, height: bar.getBoundingClientRect().height };
        }""")
        b.close()
    assert info["bar"], (site, info)
    # 벌크바 폰트 = 우리 스펙 16px(사이트 64px 상속 무력화).
    assert info["fontSize"] == "16px", (site, info)
    # 바 높이가 적대적 오염(64px×line-height 4)으로 부풀지 않음(고정 스펙 유지).
    assert info["height"] < 120, (site, info)
