"""tests/test_v71_market_smoke.py — v71 STEP5: 디폴트 마켓 스모크 표 회수(라쿠텐·야후재팬).

증상: 라쿠텐·야후재팬 등에서 버튼 미표시(퍼센티는 뜨는데 우리는 안 뜸). 근원: 디폴트 소싱처 URL 판정이
애매 URL을 무조건 'list'로 기본값 처리 → 상세 URL(상세 RE 불일치)이 목록으로 오판돼 상세 버튼 미표시.
수리: 디폴트 소싱처도 URL 명확할 때만 URL 판정, 애매하면 DOM 신호(단일 h1·갤러리·JSON-LD Product)로 낙하 →
상세면 FAB, 목록이면 벌크바. 실브라우저로 [목록 버튼·상세 버튼] 실측.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
KGP_BTN_ID = "kgp-collect-fab"
KGP_TOOLBAR_ID = "kgp-listing-toolbar"


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.131"


def test_source_contract():
    # 디폴트 소싱처 애매 URL → DOM 낙하(무조건 list 기본값 제거).
    assert "if (kgpIsDefaultSourcing()) return isDetail ? \"single\" : \"list\";" not in CS
    assert "애매하면 DOM 신호로 낙하" in CS


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


def _list_html(cur):
    cards = ""
    for i in range(1, 6):
        cards += (
            '<div class="card"><a href="/item/%d/"><img width="200" height="200" src="https://cdn.example.com/c%d.jpg"></a>'
            '<div class="title">상품 %d</div><div class="price">%s11,235</div></div>' % (i, i, i, cur)
        )
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>検索結果</title></head>'
            '<body><div class="grid">' + cards + '</div></body></html>')


def _detail_html():
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta property="og:title" content="レザー トートバッグ">'
            '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",'
            '"name":"レザー トートバッグ","image":["https://cdn.example.com/g1.jpg"],'
            '"offers":{"@type":"Offer","price":"8800","priceCurrency":"JPY"}}</script></head>'
            '<body><h1>レザー トートバッグ 本革 A4対応</h1>'
            '<div class="gallery"><img width="400" height="400" src="https://cdn.example.com/g1.jpg"></div>'
            '</body></html>')


# [사이트 | URL | 기대 오버레이] — 목록=벌크바, 상세=FAB.
MARKET_CASES = [
    ("rakuten-list",   "https://search.rakuten.co.jp/search/mall/desk/",  "list",   _list_html("¥")),
    ("rakuten-detail", "https://item.rakuten.co.jp/shopname/abc123/",     "single", _detail_html()),
    ("yahoo-list",     "https://shopping.yahoo.co.jp/search?p=desk",       "list",   _list_html("¥")),
    ("yahoo-detail",   "https://shopping.yahoo.co.jp/products/xyz-987",    "single", _detail_html()),
]


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
@pytest.mark.parametrize("name,url,expect,html", MARKET_CASES, ids=[c[0] for c in MARKET_CASES])
def test_default_market_button_attaches(name, url, expect, html):
    """레지스트리 마켓 목록→벌크바 / 상세→FAB 실측(버튼 보장)."""
    from playwright.sync_api import sync_playwright

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
        state = page.evaluate(
            "() => ({ bar: !!document.getElementById('%s'), fab: !!document.getElementById('%s') })"
            % (KGP_TOOLBAR_ID, KGP_BTN_ID)
        )
        b.close()
    if expect == "list":
        assert state["bar"], (name, state)      # 목록 → 중앙 벌크바
    else:
        assert state["fab"], (name, state)      # 상세 → 우측 단건 FAB
