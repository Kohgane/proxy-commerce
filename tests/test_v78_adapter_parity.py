"""tests/test_v78_adapter_parity.py — v78 STEP4: 어댑터 패리티(field_sources.price).

실기기 진단(ext 1.5.102): 아마존 `field_sources.price = tier2` — buybox 어댑터가 현재가를 읽었는데도
출처가 'tier2'(제네릭 휴리스틱)로 라벨. adapterMatched=true인데 price=tier2인 모순.

근본 원인(라벨링 버그): 아마존은 초기 state JSON을 캡처 못 해 tier1(`j.price`)이 빈값 → `_domPrice()`가
`_buyboxPrice()`(스코프 어댑터)로 현재가를 읽는다. 그런데 오케스트레이션은 그 provenance(scope:true)를
버리고 fieldSources가 `j.price ? tier1 : (price ? tier2 : none)`로 무조건 tier2 라벨.

수리: 가격 출처를 priceSrc로 보존 — buybox 어댑터 매치면 'buybox', 제네릭이면 'tier2'(정직).
계약: 아마존DP(buybox 현재가 구조)에서 field_sources.price == 'buybox'(adapter/buybox).
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
    assert MANIFEST["version"] == "1.5.127"


# ── source-contract: priceSrc 보존 + buybox 라벨 ──
def test_price_source_tracked():
    # buybox 어댑터 반환에 출처 마커.
    assert 'scope: true, src: "buybox"' in EX
    # 제네릭 후보에 src=dom.
    assert 'ord: i, path: _nodePath(el), src: "dom"' in EX
    # 오케스트레이션이 출처 보존(tier1/buybox/tier2).
    assert 'var priceSrc = j.price ? "tier1" : "";' in EX
    assert 'priceSrc = (dp.scope || dp.src === "buybox") ? "buybox" : "tier2";' in EX
    # fieldSources가 priceSrc 사용(무조건 tier2 라벨 제거).
    assert 'price: priceSrc ? priceSrc : (price ? "tier2" : "none"),' in EX


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


def _extract(url, body):
    from playwright.sync_api import sync_playwright
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
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
def test_amazon_price_source_is_buybox():
    """아마존DP(state JSON 없음, buybox 현재가 29.99): price=29.99·field_sources.price='buybox'(모순 해소)."""
    res = _extract("https://www.amazon.com/dp/BENKSTEST1", AMZ)
    assert (res.get("price") or "") == "29.99", res.get("price")
    fs = res.get("field_sources") or {}
    assert fs.get("price") == "buybox", ("어댑터 매치인데 buybox 아님(모순)", fs.get("price"), fs)


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_generic_dom_price_stays_tier2():
    """buybox 스코프 없는 제네릭 상세(가격만 있음): field_sources.price='tier2'(어댑터 날조 금지·정직)."""
    body = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>제네릭</title></head><body>'
            '<h1>제네릭 상품</h1><div class="product-price">₩12,000</div>'
            '<div class="gallery"><img src="https://x.com/img/p1.jpg" width="300" height="300"></div>'
            '</body></html>')
    res = _extract("https://www.someshop.com/products/detail/9001", body)
    fs = res.get("field_sources") or {}
    if res.get("price"):
        assert fs.get("price") == "tier2", ("제네릭인데 buybox 날조!", fs.get("price"))
