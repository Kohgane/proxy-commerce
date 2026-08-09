"""tests/test_v80_rakuten_gallery_folder.py — v80 STEP3: 라쿠텐 갤러리 타상품(현 상품 폴더 스코프).

오너 진단(1.5.114): 라쿠텐 갤러리에 추천 타상품 10장 혼입. v79 STEP4의 shop-slug 필터는 **같은 shop의**
타상품(다른 상품 폴더)을 통과시킴. 수리: di처럼 **현 상품 폴더 스코프** — 컨테이너(현 상품) 이미지 + og:image의
디렉토리를 유효 폴더셋으로 삼아, CDN 스윕에서 그 폴더 밖(같은 shop 타상품 folder) 제외.
계약: 라쿠텐 픽스처 갤러리 타상품 0.
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
    assert MANIFEST["version"] == "1.5.142"


# ── source-contract ──
def test_folder_scope_source():
    assert "function _rakutenFolder(u)" in EX
    assert "if (_hasFolders && !folderSet[_rakutenFolder(hiRes(s2))]) continue;" in EX
    assert "folderSet[_of] = 1;" in EX   # og:image 폴더 시드


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))


# 라쿠텐 상세: 갤러리 컨테이너=현 상품(folder /cabinet/roller/) + 같은 shop 추천 타상품(folder /cabinet/other/)
#   이 bare <img>로 노출(CDN 스윕이 잡던 leak). og:image=현 상품 대표.
_RAKUTEN = (
    '<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>Foam Roller</title>'
    '<meta property="og:image" content="https://tshop.r10s.jp/mystore/cabinet/roller/main.jpg">'
    '</head><body>'
    '<h1>フォームローラー</h1><div class="price">¥3,300</div>'
    # 갤러리 컨테이너(현 상품, folder roller) — (b) 스코프.
    '<div class="item-image-gallery">'
    '<img src="https://tshop.r10s.jp/mystore/cabinet/roller/main.jpg" width="500" height="500">'
    '<img src="https://tshop.r10s.jp/mystore/cabinet/roller/side.jpg" width="500" height="500">'
    '</div>'
    # 같은 shop 추천 타상품(folder other) — bare img, (c) 스윕이 잡던 leak. 계약: 갤러리 0.
    '<div class="recommend-band">'
    '<img src="https://tshop.r10s.jp/mystore/cabinet/other/rec1.jpg" width="300" height="300">'
    '<img src="https://tshop.r10s.jp/mystore/cabinet/other/rec2.jpg" width="300" height="300">'
    '</div>'
    # 완전 bare(추천 클래스 없음) 타상품 img — _nonProdRegion 미탐지분(진짜 leak 재현).
    '<div class="footer-widget"></div>'
    '<img src="https://tshop.r10s.jp/mystore/cabinet/other/bare-rec.jpg" width="300" height="300">'
    '</body></html>'
)

RAKUTEN_URL = "https://item.rakuten.co.jp/mystore/roller-10001/"


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
def test_rakuten_other_product_folder_excluded():
    """갤러리에 현 상품 폴더(roller)만 — 같은 shop 타상품 폴더(other) 0."""
    res = _extract(RAKUTEN_URL, _RAKUTEN)
    imgs = res.get("images") or []
    # 타상품 폴더(/cabinet/other/) 0.
    assert not any("/cabinet/other/" in u for u in imgs), ("갤러리에 타상품 폴더 혼입!", imgs)
    # 현 상품 폴더(roller) 이미지는 유지.
    assert any("/cabinet/roller/main.jpg" in u for u in imgs), ("현 상품 대표 소실!", imgs)
    assert any("/cabinet/roller/side.jpg" in u for u in imgs), ("현 상품 갤러리 소실!", imgs)
