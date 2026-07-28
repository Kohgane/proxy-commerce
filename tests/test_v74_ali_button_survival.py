"""tests/test_v74_ali_button_survival.py — v74 STEP3: 알리 버튼 생존(퍼센티 패리티).

증상: 알리 카드 호버 시 오버레이가 카드 서브트리를 통째로 재렌더 → 그 안의 우리 호버 버튼이 '증발'.
수리: 우리 오버레이(배지/호버 버튼) 소실을 감지하는 MutationObserver(100ms 디바운스)가 즉시 재부착.
계약: 호버 재렌더로 버튼이 사라져도 짧은 시간(≤~300ms) 내 재부착돼 '잔존'.
"""
from __future__ import annotations

from tests import _pw

import glob
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DETECT = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
ALI = Path("fixtures/realpages/ali-list.html").read_text(encoding="utf-8")
import json
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.128"


# ── source-contract: 오버레이 소실 즉시 재부착 관찰자 ──
def test_reattach_observer_source():
    assert "function kgpReattachOverlays()" in CS
    assert "function _isOurOverlay(n)" in CS
    assert 'n.classList.contains("kgp-card-quick") || n.classList.contains("kgp-card-chk")' in CS
    assert "}, 100);" in CS.split("function kgpReattachOverlays()")[1]   # 100ms 디바운스


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


_INJECT = """(a) => {
  const [det, cs] = a;
  window.chrome = {
    runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u, lastError: null,
               getManifest: () => ({ version: '1.5.120' }) },
    storage: { local: { get:(k,cb)=>cb&&cb({}), set(){}, onChanged:{addListener(){}} },
               sync:  { get:(k,cb)=>cb&&cb({}), set(){}, onChanged:{addListener(){}} } }
  };
  (0, eval)(det); (0, eval)(cs);
}"""

ALI_URL = "https://www.aliexpress.com/category/earbuds.html"
CARD1 = '.list-item[data-product-id="1000000001"]'


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_ali_hover_button_survives_subtree_swap():
    from playwright.sync_api import sync_playwright
    exe = _pw.chromium_hits()[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context(viewport={"width": 1200, "height": 900}).new_page()

        def handler(route):
            u = route.request.url.split("#")[0]
            if u == ALI_URL:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=ALI)
            elif ".jpg" in u:
                route.fulfill(status=200, content_type="image/svg+xml",
                              body='<svg xmlns="http://www.w3.org/2000/svg" width="220" height="220"><rect fill="#ccc" width="220" height="220"/></svg>')
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(ALI_URL, wait_until="domcontentloaded")
        page.evaluate(_INJECT, [DETECT, CS])
        page.wait_for_timeout(1400)

        # 초기: 카드1에 호버 버튼 존재 + 총 7.
        before = page.evaluate("""(sel) => ({
            total: document.querySelectorAll('.kgp-card-quick').length,
            card1: document.querySelector(sel + ' .kgp-card-quick') ? 1 : 0,
        })""", CARD1)

        # 호버 → 알리식 서브트리 재렌더로 카드1 버튼 파괴.
        page.eval_on_selector(CARD1, "el => el.dispatchEvent(new MouseEvent('mouseenter', {bubbles:true}))")
        page.wait_for_timeout(30)
        during = page.evaluate("""(sel) => ({
            total: document.querySelectorAll('.kgp-card-quick').length,
            card1: document.querySelector(sel + ' .kgp-card-quick') ? 1 : 0,
        })""", CARD1)

        # 재부착 대기(100ms 디바운스 + 여유).
        page.wait_for_timeout(320)
        after = page.evaluate("""(sel) => ({
            total: document.querySelectorAll('.kgp-card-quick').length,
            card1: document.querySelector(sel + ' .kgp-card-quick') ? 1 : 0,
        })""", CARD1)
        b.close()

    assert before["total"] == 7 and before["card1"] == 1, ("초기 전 타일 부착", before)
    assert during["card1"] == 0 and during["total"] == 6, ("호버 재렌더가 카드1 버튼을 실제로 파괴해야(회귀 재현)", during)
    assert after["card1"] == 1 and after["total"] == 7, ("소실 후 재부착 실패(알리 버튼 증발 회귀)!", after)
