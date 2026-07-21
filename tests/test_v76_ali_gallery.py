"""tests/test_v76_ali_gallery.py — v76 STEP2: 알리 갤러리·옵션 완결(v74 STEP4 종결).

증상(오너 실 하네 기준선): 알리 갤러리3·옵션0. 합성 픽스처 재현 결과 근본 결함 = **sku 컬러 스와치 썸네일이
메인 갤러리로 혼입**(대표 이미지가 상품이 아닌 색상칩) + imagePathList 미소진. 수리:
 (1) `_OPT_SWATCH_KEY`로 sku/옵션 스와치 이미지 키(skuPropertyImagePath 등)를 갤러리 라우팅에서 제외
     → option_image로만 귀속(대표 이미지=진짜 상품 첫 장).
 (2) 알리 SSR 변형 전역(_init_data_·__AER_DATA__·icRenderData·_d_c_)을 STATE_KEYS에 추가(신 레이아웃 imagePathList 소재).
계약(픽스처): imagePathList 전량(갤러리=7·스와치 0) + skuPropertyList → 옵션(Color 값 텍스트 + 값별 이미지 option_image).
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
ALI = Path("fixtures/realpages/ali-detail.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.111"


# ── source-contract: 스와치 갤러리 제외 + AE SSR 전역 ──
def test_swatch_guard_source():
    assert "var _OPT_SWATCH_KEY" in EX
    assert "skuproperty" in EX  # 스와치 키 패턴
    # 갤러리 라우팅 두 분기에 스와치 제외 적용.
    assert "var _swatch = _OPT_SWATCH_KEY.test(kv)" in EX
    assert "IMG_KEY.test(kv) && !_swatch" in EX
    assert "isProductImg(v) && !_swatch" in EX


def test_ali_state_globals_source():
    for k in ("_init_data_", "__AER_DATA__", "icRenderData", "_d_c_"):
        assert '"' + k + '"' in EX, k


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_ali_gallery_full_no_swatch_pollution():
    """실 kgp-extractor: 갤러리=imagePathList 7장(스와치 0·대표=상품 첫 장) + 옵션 Color 값 텍스트·값별 이미지."""
    from playwright.sync_api import sync_playwright
    url = "https://www.aliexpress.com/item/1005006620123.html"
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
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=ALI)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()

    imgs = res.get("images") or []
    # 갤러리 = imagePathList 전량(7) — 스와치 c-*.jpg 혼입 0.
    assert len(imgs) == 7, imgs
    assert all("mini-blender-" in u for u in imgs), imgs
    assert not any(("c-white" in u or "c-green" in u or "c-pink" in u) for u in imgs), imgs
    # 대표 이미지(첫 장) = 진짜 상품(색상칩 아님).
    assert imgs[0].endswith("mini-blender-1.jpg"), imgs[0]

    # 옵션: skuPropertyList → Color(값 텍스트) + 값별 이미지(option_image, 갤러리 아님).
    opts = {o["name"]: o for o in (res.get("options") or [])}
    assert "Color" in opts, res.get("options")
    assert opts["Color"]["values"] == ["White", "Green", "Pink"], opts["Color"]
    oi = opts["Color"].get("option_image") or {}
    assert oi.get("White", "").endswith("c-white.jpg"), oi   # 값별 이미지 = 스와치(별도 필드)
    assert oi.get("Green", "").endswith("c-green.jpg"), oi
    assert oi.get("Pink", "").endswith("c-pink.jpg"), oi
