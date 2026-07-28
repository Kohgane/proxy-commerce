"""tests/test_v76_rakuten_adapter.py — v76 STEP3: 라쿠텐(楽天市場) 상세 어댑터 신설.

증상(오너 하네 기준선): 라쿠텐 갤러리1. 근본 = 초기 JSON(JSON-LD)이 가격+대표 1장만 줘 needDom=false →
제네릭 DOM 갤러리가 안 돌아 갤러리가 1장에 그침. 수리: 호스트가 라쿠텐이면 **DOM 갤러리를 독립 수집·병합**
(갤러리 컨테이너 + 라쿠텐 CDN r10s.jp/image.rakuten.co.jp 이미지 전량, 추천/리뷰/상세 영역 제외) + 상세 본문
이미지 분리(item-detail) + `_ex=` 썸네일 파라미터 정규화(원본). 계약: img≥5 · 3핵심(제목·가격·이미지) 보장.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
RK = Path("fixtures/realpages/rakuten-detail.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.128"


# ── source-contract: 라쿠텐 어댑터 함수 + 병합 배선 + _ex 정규화 ──
def test_rakuten_adapter_source():
    assert "function _rakutenGallery()" in EX
    assert "var _RAKUTEN_CDN" in EX
    assert "function _inRakutenDetail(el)" in EX
    # 오케스트레이션에서 라쿠텐 호스트일 때 독립 병합.
    assert 'rakuten\\.(co\\.jp|com)$/.test(_rh)' in EX
    assert "var rg = _rakutenGallery();" in EX
    # _ex 썸네일 파라미터 정규화(원본).
    assert "|_ex)=" in EX


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_rakuten_gallery_full_detail_split():
    """실 kgp-extractor: 갤러리 1→전량(r10s.jp 6장·_ex 제거·대표=상품) + 상세 이미지 분리 + 추천 제외 + 3핵심."""
    from playwright.sync_api import sync_playwright
    url = "https://item.rakuten.co.jp/river-outdoor/chair-001/"
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def h(r):
            if r.request.url.split("#")[0].rstrip("/") == url.rstrip("/"):
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=RK)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()

    imgs = res.get("images") or []
    # 갤러리 전량(≥5, 6장) — 추천 rec-*.jpg 혼입 0.
    assert len(imgs) >= 5, imgs
    assert not any("rec-" in u for u in imgs), imgs
    # _ex 썸네일 파라미터 제거(원본 URL).
    assert not any("_ex" in u for u in imgs), imgs
    # 대표 = 상품 메인.
    assert res.get("image", "").endswith("item-main.jpg"), res.get("image")
    # 상세 본문 이미지 분리(갤러리와 별도 버킷).
    det = res.get("detail_images") or []
    assert any("desc-1" in u for u in det), det
    assert not any("desc-" in u for u in imgs), imgs   # 상세는 갤러리에 안 섞임
    # 3핵심 보장: 제목·가격·이미지.
    assert "折りたたみ椅子" in (res.get("title") or ""), res.get("title")
    assert res.get("price") == "3980" and res.get("currency") == "JPY", res
    assert imgs
    # 제목 사이트명 오염 0(STEP1 연동).
    for sub in ("楽天市場", "rakuten"):
        assert sub not in (res.get("title") or "")
