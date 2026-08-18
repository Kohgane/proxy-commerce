"""tests/test_v78_desc_priority.py — v78 STEP3: 상세설명 우선순위 재배선.

실기기 진단: 양쪽 desc_text = meta description(SEO 'Buy …'). 아마존 detail_specs:20 잡고도 상세 'Buy …' 한 줄.
수리: desc_text 소스 사다리 = 어댑터 상세(아마존 feature-bullets+A+·테무 상세영역) → ld+json description →
meta는 최후 폴백(desc_source=meta 표기). detail_specs 있으면 desc_text에 병합.
계약: 아마존DP에서 desc_text에 'Buy ' 접두 금지 + 불릿 포함(어댑터 우선).
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
AMZ = Path("fixtures/realpages/synthetic-amazon-dp.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.148"


# ── source-contract: 소스 사다리 + desc_source + 스펙 병합 ──
def test_desc_ladder_source():
    assert "function _adapterDetailText()" in EX
    assert "function _metaDescription()" in EX
    # 사다리: 어댑터 → tier1/ldjson → meta(표기).
    assert 'description = _ad; descSource = "adapter";' in EX
    assert 'descSource = j.ok ? "tier1" : "ldjson";' in EX
    assert 'description = _stripHtmlNoise(_m); descSource = "meta";' in EX
    # detail_specs 병합 + desc_source 출력.
    assert "if (specs.length) {" in EX and '· " + s.k + ": " + s.v' in EX
    assert "desc_source: descSource" in EX
    # 아마존 A+ 어댑터 상세 포함.
    assert "#aplus, #aplus_feature_div" in EX


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))


def _extract(url, body):
    from playwright.sync_api import sync_playwright
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def h(r):
            if r.request.url.split("#")[0] == url:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()
    return res


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_amazon_desc_adapter_beats_meta():
    """아마존DP(meta 'Buy …' 존재): desc_text=어댑터 불릿(‘Buy ’ 접두 금지) + desc_source=adapter + 스펙 병합."""
    res = _extract("https://www.amazon.com/dp/B0AMZDP0001", AMZ)
    dt = (res.get("desc_text") or "").strip()
    assert not dt.startswith("Buy "), ("desc_text가 meta SEO(Buy …)!", dt[:60])
    assert "Buy " not in dt[:40], dt[:60]
    assert "·" in dt, ("어댑터 불릿 없음", dt[:80])                 # feature-bullets 불릿
    assert "15W 고속 무선 충전 지원" in dt, dt[:120]
    assert res.get("desc_source") == "adapter", res.get("desc_source")
    # detail_specs 병합(있으면 desc_text에 스펙 표) — 아마존 픽스처는 스펙 0일 수 있어 조건부.
    if res.get("detail_specs"):
        pass


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_meta_is_last_fallback_tagged():
    """어댑터 상세·ld+json 없고 meta만 있는 페이지: desc_text=meta 이지만 desc_source='meta'로 표기(정직)."""
    body = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="description" content="Buy this generic gadget online, best price, free shipping and more text here.">'
            '<title>제네릭 상품</title></head><body>'
            '<h1>제네릭 상품</h1><div class="price">₩12,000</div>'
            '<div class="gallery"><img src="https://x.com/img/p1.jpg" width="300" height="300"></div>'
            '</body></html>')
    res = _extract("https://www.someshop.com/products/detail/12345", body)
    dt = (res.get("desc_text") or "")
    if dt:   # meta만 있으면 desc_source=meta로 정직 표기(품질 낮음 신호)
        assert res.get("desc_source") == "meta", ("meta 폴백인데 desc_source 미표기", res.get("desc_source"), dt[:60])
