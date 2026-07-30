"""tests/test_v81_rakuten_top.py — v81 STEP4: 라쿠텐 톱 오수집 차단 + 추천/이력 위젯 블록리스트.

오너 실기기: www.rakuten.co.jp 톱에서 per-tile 수집버튼 주입 + data-kgp-skip 135건. 톱은 상품/목록
페이지가 아니므로 후보 0이어야 한다. 足あと(#riAshiato)·あなたにおすすめ([id^=tabpanel-recommend])·
'閲覧した商品からのおすすめ' 헤딩 섹션 타일을 명시 제외(skip=recommend-widget). 감지 자체는 유지.

계약(CI 게이트): (1) per-tile 수집버튼 0 (2) 저장 후보 0 (3) skip 총계 >0.
STEP C: no-price-no-url → no-item-url / no-price 분리.
"""
from __future__ import annotations

from tests import _pw

import glob
import json
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DETECT = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
RTOP = Path("fixtures/realpages/rakuten-top.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


# ── source-contract ──
def test_recommend_widget_blocklist_source():
    assert "function _kgpInRecommendWidget(el)" in CS
    assert 'id === "riAshiato"' in CS
    assert "tabpanel-recommend" in CS
    assert "閲覧した商品からのおすすめ" in CS and "あなたにおすすめ" in CS
    # 블록리스트는 후보 제외만(감지 유지) — 제네릭 경로에서 skip 사유로만 적용.
    assert 'if (_kgpInRecommendWidget(card)) { _kgpExcl.region++; _kgpMarkSkip(card, "recommend-widget"); continue; }' in CS
    # STEP C: 사유 분리.
    # 사유 분리 = 동작 계약(옛 고정핀은 v86 STEP5에서 사유가 늘자 부서졌다 — 문장이 아니라 분기를 본다).
    seg = CS.split("if (!pr.price && !_kgpIsProductHref(href)) {")[1].split("continue;")[0]
    assert '"no-price"' in seg and '"no-item-url"' in seg
    assert '_kgpIsProductHref(href) ?' in seg
    assert "no-price-no-url" not in CS   # 옛 뭉뚱그린 사유 제거


def test_fixture_present_and_top_page():
    assert 'rel="canonical" href="https://www.rakuten.co.jp/"' in RTOP
    assert 'id="riAshiato"' in RTOP and 'id="tabpanel-recommend-0"' in RTOP
    assert "閲覧した商品からのおすすめ" in RTOP


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

RTOP_URL = "https://www.rakuten.co.jp/"


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_rakuten_top_no_candidates_no_buttons_skips_reported():
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
            if u == RTOP_URL:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=RTOP)
            elif ".jpg" in u:
                route.fulfill(status=200, content_type="image/svg+xml",
                              body='<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#ccc"/></svg>')
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(RTOP_URL, wait_until="domcontentloaded")
        page.evaluate(_INJECT, [DETECT, CS])
        page.wait_for_timeout(1500)
        r = page.evaluate("""() => {
            const cards = (typeof kgpFindCards === 'function') ? kgpFindCards() : [];
            // skip 사유는 DOM data-kgp-skip 속성으로 관측(모듈 lexical 변수는 evaluate 경계 밖에서 미노출).
            const skip = {};
            document.querySelectorAll('[data-kgp-skip]').forEach((e) => {
              const k = e.getAttribute('data-kgp-skip'); skip[k] = (skip[k] || 0) + 1;
            });
            let total = 0; for (const k in skip) total += skip[k];
            return {
              cards: cards.length,
              perTileBtns: document.querySelectorAll('.kgp-card-chk, .kgp-card-quick').length,
              bar: !!document.getElementById('kgp-listing-toolbar'),
              skip: skip, skipTotal: total,
            };
        }""")
        b.close()
    # (2) 저장 후보 0 — 톱의 모든 상품 타일은 추천/이력 위젯 소속(제외).
    assert r["cards"] == 0, ("톱에서 후보 검출(오수집)!", r)
    # (1) per-tile 수집버튼 0 · 벌크바 없음.
    assert r["perTileBtns"] == 0, ("톱 타일에 수집버튼 오탐 부착!", r)
    assert r["bar"] is False, r
    # (3) skip 총계 >0 — 위젯 타일이 recommend-widget으로 정직 집계.
    assert r["skipTotal"] > 0, ("스킵 사유 집계 0(자가보고 실패)!", r)
    assert r["skip"].get("recommend-widget", 0) >= 6, ("추천/이력 위젯 6타일 제외 누락!", r)
