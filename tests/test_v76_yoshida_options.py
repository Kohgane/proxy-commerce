"""tests/test_v76_yoshida_options.py — v76 STEP4: 요시다 옵션(컬러 스와치) + 갤러리 스코프 재확인.

증상(오너 하네 기준선): 요시다 옵션0. 근본 = 색상 스와치가 `<a data-color><img alt>` 구조라 기존 스와치
그룹 값 수집 셀렉터(data-value/텍스트)에 안 걸림. 수리: 스와치 값을 data-color/data-option/data-name·
자식 img[alt]에서도 읽고, 일본어 축명(カラー/サイズ)을 인식·한글 정규화. 갤러리 스코프(연관상품·스와치
썸네일 제외)는 이미 정상 — 재확인 계약.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
YO = Path("fixtures/realpages/yoshida-detail.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.126"


# ── source-contract: 스와치 값 확장 + 일본어 축명 ──
def test_swatch_value_source():
    # 스와치 값: data-color/data-option/data-name + img[alt].
    assert 'a[data-color],[data-color],[data-option],[data-name]' in EX
    assert 'el.querySelector("img[alt]")' in EX
    assert 'getAttribute("data-color")' in EX
    # 일본어 축명 인식 + 한글 정규화.
    assert "カラー" in EX and "サイズ" in EX
    assert "function _normAxis(name)" in EX
    assert "_push(gm ? _normAxis(gm[0]) : " in EX


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_yoshida_color_option_and_gallery_scope():
    """실 kgp-extractor: 색상 스와치 옵션 수집(opt>=1) + 갤러리 스코프(연관상품·스와치 썸네일 제외)."""
    from playwright.sync_api import sync_playwright
    url = "https://www.yoshidakaban.com/products/detail/12345"
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
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=YO)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()

    # 옵션: 색상 스와치(opt>=1) — 값 텍스트 = 색상명.
    opts = {o["name"]: o["values"] for o in (res.get("options") or [])}
    assert opts, res.get("options")
    color = opts.get("색상") or next(iter(opts.values()))
    assert "ブラック" in color and "ネイビー" in color and "シルバー" in color, opts

    # 갤러리 스코프 재확인: 상품 갤러리 6장만 — 연관상품(/rel/)·스와치 썸네일(/sw/) 혼입 0.
    imgs = res.get("images") or []
    assert len(imgs) == 6, imgs
    assert not any("/rel/" in u for u in imgs), imgs
    assert not any("/sw/" in u for u in imgs), imgs
    # 대표 = 상품 첫 장.
    assert res.get("image", "").endswith("goods/1.jpg"), res.get("image")
    # 3핵심 + 제목 사이트명 0(STEP1 연동).
    assert "PORTER TANKER" in (res.get("title") or "")
    assert res.get("price") == "19800" and res.get("currency") == "JPY"
    assert "吉田カバン" not in (res.get("title") or "")
