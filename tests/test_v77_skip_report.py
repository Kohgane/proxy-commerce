"""tests/test_v77_skip_report.py — v77 STEP2: 미부착 타일 자가보고.

자격 필터에서 탈락한 타일에 `data-kgp-skip="사유"`(no-asin/non-product/dup/parse-fail/no-url…) 부여 →
'왜 이 타일만 버튼이 없지?'를 속성 하나로 판독 + 디버그 패널(진단 번들 excl/skipStats) 사유별 카운트.
계약: 스캔된 타일 전부 [버튼(data-kgp=done) or 스킵 사유(data-kgp-skip) 1개] — 무표식 타일 0.
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
SEARCH = Path("fixtures/realpages/amazon-search.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.140"


# ── source-contract: 스킵 마킹 + 사유 집계 + 진단 노출 ──
def test_skip_report_source():
    assert "function _kgpMarkSkip(el, reason)" in CS
    assert 'el.setAttribute("data-kgp-skip", reason)' in CS
    assert "function _kgpClearSkip(el)" in CS
    assert "_kgpSkipReset()" in CS                       # 스캔마다 초기화
    # 아마존 어댑터 탈락 지점 사유 부여.
    #   v86-B: 광고(sspa) 타일은 payload에서 ASIN을 복원하고, 그래도 못 뽑으면 'no-asin'과 원인이 다르므로
    #   'ad-sspa-fail'로 분리한다. 옛 고정핀(`_kgpMarkSkip(el, "no-asin")` 정확 일치)은 사유가 하나 늘자
    #   부서졌다 — 대상은 문장이 아니라 **동작**이므로 "그 분기가 두 사유를 구분해 남긴다"로 본다.
    _asin_seg = CS.split("if (!/^[A-Z0-9]{10}$/.test(asin)) {")[1].split("return;")[0]
    assert "_kgpMarkSkip(el," in _asin_seg
    assert '"no-asin"' in _asin_seg and '"ad-sspa-fail"' in _asin_seg
    assert '_kgpMarkSkip(el, "non-product")' in CS
    assert '_kgpMarkSkip(el, "parse-fail")' in CS
    # 제네릭 탈락 지점.
    assert '_kgpMarkSkip(_skipEl, "no-url")' in CS
    # 진단 번들에 사유별 집계.
    assert "skipStats: _kgpSkipStats" in CS


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


_INJECT = """(a) => {
  const [detect, cs] = a;
  window.chrome = { runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u,
      lastError: null, getManifest: () => ({ version: '1.5.120' }) },
    storage: { local: { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } },
               sync:  { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } } } };
  (0, eval)(detect); (0, eval)(cs);
}"""


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_every_tile_buttoned_or_skip_marked():
    """스캔된 전 타일: 버튼(data-kgp) 또는 스킵 사유(data-kgp-skip) — 무표식 0. 비상품 위젯=no-asin."""
    from playwright.sync_api import sync_playwright
    url = "https://www.amazon.com/s?k=ultraslim+phone+grip"
    exe = _pw.chromium_hits()[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def h(r):
            if r.request.url.split("#")[0] == url:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=SEARCH)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        page.evaluate(_INJECT, [DETECT, CS])
        page.wait_for_timeout(1300)
        r = page.evaluate("""() => {
            const tiles = document.querySelectorAll('[data-component-type="s-search-result"]');
            let unmarked = 0, buttoned = 0, skipped = 0;
            const skipReasons = {};
            tiles.forEach((t) => {
                const hasBtn = t.getAttribute('data-kgp') === 'done' || !!t.querySelector('.kgp-card-quick');
                const skip = t.getAttribute('data-kgp-skip');
                if (hasBtn) buttoned++;
                else if (skip) { skipped++; skipReasons[skip] = (skipReasons[skip]||0)+1; }
                else unmarked++;
            });
            // 비상품 위젯(data-asin="")의 스킵 사유.
            const widget = document.querySelector('[data-asin=""][data-component-type="s-search-result"]');
            return { total: tiles.length, buttoned, skipped, unmarked, skipReasons,
                     widgetSkip: widget ? widget.getAttribute('data-kgp-skip') : 'no-widget',
                     noAsinDom: document.querySelectorAll('[data-kgp-skip="no-asin"]').length };
        }""")
        b.close()

    # 무표식 타일 0 — 전 타일이 버튼 또는 스킵 사유.
    assert r["unmarked"] == 0, ("무표식 타일 존재(자가보고 실패)!", r)
    assert r["buttoned"] == 24, ("상품 타일 버튼 수 불일치", r)
    assert r["skipped"] >= 1, ("스킵 타일 미표식", r)
    # 비상품 위젯(ASIN 없음)은 no-asin 사유(속성 하나로 판독).
    assert r["widgetSkip"] == "no-asin", ("비상품 위젯 스킵 사유 오류", r)
    # 사유별 집계(DOM 관측) — no-asin 최소 1.
    assert r["noAsinDom"] >= 1, ("no-asin 스킵 타일 미표식", r)
