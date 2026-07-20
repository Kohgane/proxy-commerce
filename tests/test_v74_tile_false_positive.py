"""tests/test_v74_tile_false_positive.py — v74 STEP1: 타일 오탐 필터(카테고리 내비 제외).

증상: 요시다 카테고리 아이콘 줄에 우리 수집 버튼 오탐 부착. 근본: v43-2의 느슨한 _kgpIsDetailHref가
/products/<카테고리>(가격 없음)까지 통과. 수리: 타일 자격 = [상품 URL 패턴 or 가격] 중 1 필수 + 이미지.
카테고리 URL(가격없음)·내비/메뉴 영역은 제외. 계약: 카테고리 줄 버튼 0 · 상품 타일 전부 부착.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DETECT = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
YOSHIDA = Path("fixtures/realpages/yoshida-list.html").read_text(encoding="utf-8")
import json
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.106"


# ── source-contract: 엄격 상품 URL + 카테고리/내비 제외 ──
def test_strict_qualification_source():
    assert "function _kgpIsProductHref(href)" in CS
    assert "function _kgpIsCategoryHref(href)" in CS
    assert "function _kgpInNavRegion(el)" in CS
    # 자격 판정이 엄격판(_kgpIsProductHref) 사용 — 느슨한 _kgpIsDetailHref 아님.
    assert "if (!pr.price && !_kgpIsProductHref(href))" in CS
    assert "if (_kgpInNavRegion(card))" in CS


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
               getManifest: () => ({ version: '1.5.106' }) },
    storage: { local: { get:(k,cb)=>cb&&cb({}), set(){}, onChanged:{addListener(){}} },
               sync:  { get:(k,cb)=>cb&&cb({}), set(){}, onChanged:{addListener(){}} } }
  };
  (0, eval)(det); (0, eval)(cs);
}"""

YOSHIDA_URL = "https://www.yoshidakaban.com/products/list"


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_category_rows_get_no_buttons_products_all_buttoned():
    from playwright.sync_api import sync_playwright
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context(viewport={"width": 1200, "height": 800}).new_page()

        def handler(route):
            u = route.request.url.split("#")[0]
            if u == YOSHIDA_URL:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=YOSHIDA)
            elif ".jpg" in u:
                route.fulfill(status=200, content_type="image/svg+xml",
                              body='<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#ccc"/></svg>')
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(YOSHIDA_URL, wait_until="domcontentloaded")
        page.evaluate(_INJECT, [DETECT, CS])
        page.wait_for_timeout(1400)
        r = page.evaluate("""() => ({
            genericCount: (typeof _kgpGenericCards === 'function') ? _kgpGenericCards().length : -1,
            catBtns: document.querySelectorAll('nav .kgp-card-chk, nav .kgp-card-quick, .category-tiles .kgp-card-chk, .category-tiles .kgp-card-quick').length,
            prodBtns: document.querySelectorAll('.product .kgp-card-chk').length,
            totalBadges: document.querySelectorAll('.kgp-card-chk').length,
            bar: !!document.getElementById('kgp-listing-toolbar'),
        })""")
        b.close()
    # 계약: 카테고리 줄 버튼 0 · 상품 타일 6 전부 부착 · 오탐 0.
    assert r["catBtns"] == 0, ("카테고리 내비 줄 오탐 부착 회귀!", r)
    assert r["prodBtns"] == 6, ("상품 타일 일부 미부착!", r)
    assert r["genericCount"] == 6, ("상품 감지 수 불일치(카테고리 혼입/상품 누락)!", r)
    assert r["totalBadges"] == 6, ("총 배지=상품 수여야(오탐 0)!", r)
    assert r["bar"] is True, r
