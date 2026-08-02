"""tests/test_v79_sku_sanitize.py — v79 STEP2: sku 정제(빈 항목 제거 + 동일 spec dedupe).

오너 진단(1.5.108): 테무·라쿠텐 sku가 2~3배 반복(_walk가 같은 sku 배열 재방문) + 빈 sku({spec:[],price:''}).
수리: _skusToOptions 직전에 res.skus를 정제 — 빈 항목(spec 없고 price 없음) 제거 + 동일 spec 서명 dedupe
(무가격보다 유가격 우선). 계약: sku에 빈 항목 0·중복 0. 옵션(axisMap 파생)은 무영향(이미 dedup).
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.136"


# ── source-contract: sku 정제 블록 ──
def test_sku_sanitize_source():
    assert "v79 STEP2: sku 정제" in EX
    assert "if (!_spec.length && !_price) continue;" in EX            # 빈 sku 제거
    assert "if (!_prev.price && _price) clean[idx[_key]] = _sk;" in EX  # 무가격→유가격 교체
    assert "res.skus = clean;" in EX
    assert "res.options = _skusToOptions(axisMap, res.skus);" in EX     # 정제 후 옵션 변환


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


# 테무식 상태: 동일 spec 3회 반복 + 빈 sku 1개. dedup 후 2건, 옵션은 색상[2]·사이즈[2].
_DUP_STATE = """
window.__INITIAL_STATE__ = { store: { goods: { title: "테무 캣타워 (다층 원목)",
  price_str: "40,603원",
  sku_list: [
    { sku_id: 1, sku_price: "40603", spec_list: [ { spec_key: "색상", spec_value: "베이지" }, { spec_key: "사이즈", spec_value: "대형" } ] },
    { sku_id: 1, sku_price: "40603", spec_list: [ { spec_key: "색상", spec_value: "베이지" }, { spec_key: "사이즈", spec_value: "대형" } ] },
    { sku_id: 1, sku_price: "40603", spec_list: [ { spec_key: "색상", spec_value: "베이지" }, { spec_key: "사이즈", spec_value: "대형" } ] },
    { sku_id: 2, sku_price: "38000", spec_list: [ { spec_key: "색상", spec_value: "그레이" }, { spec_key: "사이즈", spec_value: "중형" } ] },
    { sku_id: 2, sku_price: "38000", spec_list: [ { spec_key: "색상", spec_value: "그레이" }, { spec_key: "사이즈", spec_value: "중형" } ] },
    { sku_id: 0, sku_price: "", spec_list: [] }
  ] } } };
"""

_BODY = (
    '<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>테무 캣타워</title>'
    "<script>" + _DUP_STATE + "</script></head><body>"
    '<h1>테무 캣타워 (다층 원목)</h1><div class="price">40,603원</div>'
    '<div class="gallery"><img src="https://img.kwcdn.com/product/abc/main.jpg" width="400" height="400"></div>'
    "</body></html>"
)


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
def test_temu_dup_and_empty_skus_cleaned():
    """동일 spec 3+2회 반복 + 빈 sku 1 → skus 2건(빈 0·중복 0), 옵션 색상[2]·사이즈[2] 유지."""
    res = _extract("https://www.temu.com/kr/cat-tower-g-1.html", _BODY)
    skus = res.get("skus") or []
    # 빈 항목 0.
    for sk in skus:
        assert (sk.get("spec") or []) or (sk.get("price") or ""), ("빈 sku 잔존!", sk)
    # 중복 0 — spec 서명 유일.
    sigs = ["".join(sorted(sk.get("spec") or [])) for sk in skus]
    assert len(sigs) == len(set(sigs)), ("동일 spec 중복 잔존!", sigs)
    assert len(skus) == 2, ("dedup 후 2건이어야(3+2 반복→2, 빈 1 제거)", len(skus), skus)
    # 옵션은 무영향(axisMap dedup) — 색상[2]·사이즈[2].
    opts = {o["name"]: o["values"] for o in (res.get("options") or [])}
    assert set(opts.get("색상") or []) == {"베이지", "그레이"}, opts
    assert set(opts.get("사이즈") or []) == {"대형", "중형"}, opts
