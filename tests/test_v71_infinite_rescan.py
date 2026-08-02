"""tests/test_v71_infinite_rescan.py — v71 STEP4: 무한스크롤 재스캔 + 버튼 단일 스펙.

증상: 알리 등 첫 화면만 버튼, 스크롤 시 미부착 + 버튼 과대(사이트 CSS 간섭).
수리: ①MutationObserver+스크롤로 신규 타일 상시 재부착(디바운스 300ms, 부착 스킵, 가상화 재사용 노드 url 갱신)
②버튼 크기·형태 속성에 !important(인라인+!important 최고 특이성)로 사이트 불문 단일 스펙 강제.
"""
from __future__ import annotations

from tests import _pw

import glob
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
import json
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.135"


def test_source_contract():
    # 재스캔 상시화(목록 모드 게이트·디바운스·멱등).
    assert "function kgpRescanTiles()" in CS
    assert 'if (kgpPageType() !== "list") return;' in CS
    assert 'window.addEventListener("scroll", kgpRescanTiles, { passive: true });' in CS
    assert "new MutationObserver(kgpRescanTiles)" in CS
    # 가상화 재사용 노드: 배지 url 갱신 + 클릭이 dataset.url 사용.
    assert "existing.dataset.url = c.url;" in CS
    assert "kgpToggleCard(badge.dataset.url, badge, badge._kgpEl || c.el);" in CS
    # 버튼 단일 스펙: !important.
    assert CS.count("!important") >= 20
    # v80 STEP1: 선택 체크박스는 shadow DOM 자체 그림(텍스트 배지 폐기) — 스타일 이중 주입.
    assert "function _kgpBuildCheckbox(host, selected)" in CS
    assert "host.attachShadow({ mode: \"open\" })" in CS
    assert "root.adoptedStyleSheets = [sh]" in CS and 'document.createElement("style")' in CS


def test_button_style_has_important_node():
    # v80 STEP1: kgpCardBadgeStyle = 체크박스 호스트(위치·크기 컨테이너). 크기/위치/커서 !important(사이트 CSS 무력화).
    #   가시 UI(배경·테·체크)는 shadow DOM CSS로 이동 → 호스트엔 position/width/height/cursor만.
    m = re.search(r"function kgpCardBadgeStyle\(selected\) \{.*?\n\}", CS, re.S)
    assert m
    import shutil as _sh
    if not _sh.which("node"):
        pytest.skip("node 미설치")
    harness = ("var _KGP_RESET=\"all:initial !important;box-sizing:border-box !important;\";var KGP_TOUCH=false;\n"
               + m.group(0) + "\nprocess.stdout.write(kgpCardBadgeStyle(false));\n")
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        css = r.stdout.strip()
    finally:
        Path(f.name).unlink()
    for prop in ("position:absolute", "width:22px", "height:22px", "cursor:pointer", "box-sizing:"):
        assert (prop in css), css
    assert css.count("!important") >= 6, css


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


_CHROME_STUB = """
window.chrome = {
  runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u, lastError: null },
  storage: {
    local: { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } },
    sync:  { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } }
  }
};
"""


def _list_html():
    cards = ""
    for i in range(1, 6):
        cards += (
            '<div class="card"><a href="/goods/%d"><img width="200" height="200" '
            'src="https://img.kwcdn.com/c%d.jpg"></a><div class="title">상품 %d 데스크</div>'
            '<div class="price">₩11,235</div></div>' % (i, i, i)
        )
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>검색결과</title></head>'
            '<body><div class="grid">' + cards + '</div></body></html>')


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_new_tiles_get_badges_on_scroll_inject():
    """목록 5타일 → 배지 5개, 스크롤로 3타일 유입 → 재스캔이 신규 타일에도 배지(8개)."""
    from playwright.sync_api import sync_playwright

    url = "https://www.temu.com/search_result.html?q=desk"
    html = _list_html()
    exe = _pw.chromium_hits()[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        ctx = b.new_context()
        page = ctx.new_page()
        page.add_init_script(_CHROME_STUB)

        def handler(route):
            if route.request.url.split("#")[0] == url:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(url, wait_until="domcontentloaded")
        page.evaluate("(cs)=>{ (0,eval)(cs); }", CS)
        page.wait_for_timeout(600)
        before = page.evaluate("document.querySelectorAll('.kgp-card-chk').length")
        # 무한스크롤 유입: 카드 3개 추가.
        page.evaluate(
            """() => {
                const g = document.querySelector('.grid');
                for (let i = 6; i <= 8; i++) {
                    const d = document.createElement('div'); d.className = 'card';
                    d.innerHTML = '<a href="/goods/' + i + '"><img width="200" height="200" src="https://img.kwcdn.com/c' + i + '.jpg"></a>'
                        + '<div class="title">상품 ' + i + ' 데스크</div><div class="price">₩11,235</div>';
                    g.appendChild(d);
                }
            }"""
        )
        page.wait_for_timeout(700)   # 디바운스 300ms + 여유
        after = page.evaluate("document.querySelectorAll('.kgp-card-chk').length")
        b.close()
    assert before >= 5, before
    assert after >= 8, (before, after)   # 신규 3타일에도 배지 부착(스크롤 재스캔)
