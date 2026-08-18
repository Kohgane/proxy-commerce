"""tests/test_v87_597_rakuten_tile_price.py — 백로그 #597: 라쿠텐 리스트 타일 가격 간이 포착.

프리즈 해제: 실 검색-리스트 스냅샷(fixtures/realpages/diag/kgp-snapshot-search-rakuten*.html).
근원: ① `_kgpPrice`가 '円'(엔 한자) 접미 미처리 ② 가격이 감지 카드 바깥 상위 타일(.searchresultitem)에 있음.
수리: 円→JPY + 라쿠텐 item 타일 한정 tile-scoped 조상 가격 스코프(교차 오염 가드 `item.rakuten 링크>2 중단`).
계약: 34타일(이 픽스처 35) keep-set 불변(가격 전/후 동일) · 가격 전부 채워짐(전 0) · distinct(교차 오염 0).
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

from tests import _pw

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DET = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
_FIX = glob.glob("fixtures/realpages/diag/kgp-snapshot-search-rakuten*.html")


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.148"


def test_source_contract():
    # ① 円(엔 한자) 접미 → JPY.
    assert "(?:원|円)" in CS and '"円": "JPY"' in CS
    # ② 라쿠텐 item 타일 한정 조상 가격 스코프 + 교차 오염 가드.
    assert 'href.indexOf("item.rakuten.co.jp") >= 0' in CS
    assert 'a[href*="item.rakuten.co.jp"]\').length > 2) break' in CS


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


_INJECT = """(a)=>{const[det,cs]=a;window.chrome={runtime:{id:'x',onMessage:{addListener(){}},sendMessage(){},getURL:u=>u,lastError:null,getManifest:()=>({version:'1.5.148'})},storage:{local:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}},sync:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}}}};(0,eval)(det);(0,eval)(cs);}"""
_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#ccc"/></svg>'
_URL = "https://search.rakuten.co.jp/search/mall/test/"


@pytest.mark.skipif(not _FIX, reason="라쿠텐 검색 스냅샷 픽스처 없음")
@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_rakuten_tiles_priced_realpage():
    HTML = Path(_FIX[0]).read_text(encoding="utf-8")
    from playwright.sync_api import sync_playwright
    exe = _pw.chromium_hits()[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context(viewport={"width": 1280, "height": 900}).new_page()

        def h(route):
            u = route.request.url.split("#")[0]
            if u.rstrip("/") == _URL.rstrip("/"):
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=HTML)
            elif any(x in u for x in [".jpg", ".png", ".webp", ".gif", ".svg"]):
                route.fulfill(status=200, content_type="image/svg+xml", body=_SVG)
            else:
                route.abort()
        page.route("**/*", h)
        page.goto(_URL, wait_until="domcontentloaded")
        page.evaluate(_INJECT, [DET, CS])
        page.wait_for_timeout(1800)
        r = page.evaluate("""()=>{const c=_kgpGenericCards();
          const priced=c.filter(x=>x.price&&x.price.length);
          const uniq=new Set(priced.map(x=>x.price));
          return{count:c.length, priced:priced.length, jpy:c.filter(x=>x.currency==='JPY').length,
                 anchors:c.filter(x=>(x.url||'').indexOf('item.rakuten.co.jp')>=0).length, distinct:uniq.size};}""")
        b.close()
    # keep-set(감지) 불변 — 이 픽스처 35타일 전부 item.rakuten 앵커.
    assert r["count"] == 35, r
    assert r["anchors"] == 35, r
    # 가격이 전부 채워짐(수리 전 0). 전부 JPY.
    assert r["priced"] == 35, r
    assert r["jpy"] == 35, r
    # 교차 오염 0 — 한 가격을 전 타일에 복사하지 않았다(distinct 다수).
    assert r["distinct"] >= 20, r
