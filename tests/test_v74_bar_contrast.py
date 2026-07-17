"""tests/test_v74_bar_contrast.py — v74 STEP2: 벌크바 대비 자립(다크/라이트 헤더 동일 가독).

증상: 다크 헤더(요시다) 위 벌크바 버튼이 저대비로 '유령화'. 근본: 버튼 스타일이 all:initial(격리) 뒤에
color를 **비-!important**로 줘서, all:initial의 color:initial(검정)이 이겨 버튼 텍스트가 검정 → 다크 바에서 소멸.
수리: 벌크바 배경(먹)·텍스트(웜화이트)·버튼 색/보더 전부 !important(자립 스타일) → 사이트 상속·색 규칙 차단,
다크/라이트 헤더 모두 동일 렌더.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DETECT = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
SEARCH = Path("fixtures/realpages/amazon-search.html").read_text(encoding="utf-8")
import json
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.97"


# ── source-contract: 벌크바 색 전부 !important(자립) ──
def test_bar_colors_all_important_source():
    seg = CS.split("function kgpBuildToolbar()")[1].split("bar.addEventListener")[0]
    assert 'background:#1a1714 !important' in seg and 'color:#f5efe3 !important' in seg   # 바 먹/웜화이트
    assert 'color:#e7ddc9 !important' in seg    # ghost 버튼 텍스트
    assert 'color:#e8d6a8 !important' in seg    # gold 버튼 텍스트
    assert 'background:#119a8e !important;color:#fff !important' in seg   # teal 채움
    assert 'color:#ecdcb0 !important' in seg    # 그립 타이틀


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


_INJECT = """(a) => {
  const [det, cs] = a;
  window.chrome = {
    runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u, lastError: null,
               getManifest: () => ({ version: '1.5.97' }) },
    storage: { local: { get:(k,cb)=>cb&&cb({}), set(){}, onChanged:{addListener(){}} },
               sync:  { get:(k,cb)=>cb&&cb({}), set(){}, onChanged:{addListener(){}} } }
  };
  (0, eval)(det); (0, eval)(cs);
}"""

AMZ_URL = "https://www.amazon.com/s?k=x"
# 적대적 사이트 CSS: 다크 헤더가 버튼/스팬/strong 색을 강제(!important)로 오염 시도 → 자립 스타일이 이겨야.
DARK_HOSTILE = "<style>button,span,strong{color:#111 !important;background:#000 !important !important}html,body{background:#0a0a0a;color:#111}</style>"
LIGHT_HOSTILE = "<style>button,span,strong{color:#fff !important;background:#fff !important}html,body{background:#fff;color:#eee}</style>"

# 우리 벌크바 색 계약(자립 — 사이트 오염 무력).
EXPECT = {
    "ghost": "rgb(231, 221, 201)",   # #e7ddc9
    "gold": "rgb(232, 214, 168)",    # #e8d6a8
    "teal": "rgb(255, 255, 255)",    # #fff on #119a8e
    "bg": "rgb(26, 23, 20)",         # #1a1714
}


def _run(hostile):
    from playwright.sync_api import sync_playwright
    html = SEARCH.replace("<body>", hostile + "<body>")
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def handler(route):
            u = route.request.url.split("#")[0]
            if u == AMZ_URL:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            elif ".jpg" in u:
                route.fulfill(status=200, content_type="image/svg+xml",
                              body='<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180"><rect fill="#ccc" width="180" height="180"/></svg>')
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(AMZ_URL, wait_until="domcontentloaded")
        page.evaluate(_INJECT, [DETECT, CS])
        page.wait_for_timeout(1200)
        r = page.evaluate("""() => {
            const bar = document.getElementById('kgp-listing-toolbar');
            const pick = (act) => { const el = document.querySelector('.kgp-tb-btn[data-act="'+act+'"]'); return el ? getComputedStyle(el).color : null; };
            return {
                barBg: bar ? getComputedStyle(bar).backgroundColor : null,
                barColor: bar ? getComputedStyle(bar).color : null,
                ghost: pick('all-sel'),
                gold: pick('collect-sel'),
                teal: pick('collect-all'),
                grip: (function(){ const s = document.querySelector('#kgp-tb-grip strong'); return s ? getComputedStyle(s).color : null; })(),
            };
        }""")
        b.close()
    return r


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
@pytest.mark.parametrize("name,hostile", [("dark", DARK_HOSTILE), ("light", LIGHT_HOSTILE)],
                         ids=["dark-header", "light-header"])
def test_bar_self_contained_contrast(name, hostile):
    r = _run(hostile)
    assert r["barBg"] == EXPECT["bg"], (name, "바 배경이 먹(자립) 아님", r)
    assert r["ghost"] == EXPECT["ghost"], (name, "ghost 버튼 유령화(색 오염)!", r)
    assert r["gold"] == EXPECT["gold"], (name, "gold 버튼 유령화!", r)
    assert r["teal"] == EXPECT["teal"], (name, "teal 버튼 텍스트 오염!", r)
    assert r["grip"] == "rgb(236, 220, 176)", (name, "그립 타이틀 오염!", r)  # #ecdcb0
