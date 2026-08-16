"""tests/test_v86_v2_amazon_gallery.py — v86-V2 아마존 상세 갤러리 실기기 재현·수리.

## 오너 실기기 확정(재조사 금지)
1.5.145 amazon dp(SUPERONE) single·adapterMatched=True: gallery=**1장**(대표 713q1zpatL만).
DOM 실측: #altImages 존재, 썸네일 버튼 7, 썸네일 ID 다수 — **소재는 있는데 수집이 안 집는다**.
v86-V 2항의 "실추출 og 1 + #altImages 5 → ≥5장"은 오너 환경에서 재현 안 됨(공허한 그린).

## 근원 (실크롬 재현으로 특정)
v86-V 계약은 altImages 썸네일을 **비로드**(routed 픽스처 → naturalWidth=0)로 넣어, `_amazonGallery`의
`naturalWidth < 40` 가드를 우연히 통과했다(false green). 실 아마존 썸네일은 **디자인상 ~38px로 렌더**되어
naturalWidth=38 → 이 가드(1px·아이콘 배제용)가 **정품 썸네일 7장을 통째로 배제** → 대표 1장만 생존.
- 실크롬 재현(38px 실로드 `_AC_US40_` 썸네일): 수리 前 gallery=**1**, 수리 後 **8**. (data: 지연 placeholder는
  복구할 URL 자체가 없어 1 유지 — 오너 '썸네일 ID 다수 in DOM' = 실 URL 존재 → naturalWidth 가드가 원인.)

## 부검 (V 계약이 왜 이 분기를 놓쳤나) — 1줄
> v86-V 계약은 썸네일을 비로드(naturalWidth=0)로 픽스처링해 `naturalWidth<40` 가드가 우회됐고, 실기기의
> **로드된 38px 썸네일** 분기(가드 발동)를 실브라우저로 강제하지 않아 false green이 났다.

## 수리 (extractor DOM 갤러리만 — tier1/kgp-net 무수정)
`_amazonGallery`: 크기 토큰(`_AC_US40_` 등)이 있어 hiRes가 대형 원본으로 승격하는 URL(hr!==src)은 **크기
가드를 건너뛰고**, 토큰 없는 고정크기 이미지에만 1px/아이콘 가드 적용. 판별은 썸네일 렌더 크기가 아니라
**승격된 URL의 상품성**으로(= `_bestImgSrc` 설계와 일치, 신규 발명 0).
"""
from __future__ import annotations

import base64
import glob
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
import json
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))

# 38x38 실 PNG(로드되면 naturalWidth=38 → 옛 가드 발동 조건). base64.
_PNG38 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAACYAAAAmCAYAAACoPemuAAAAHElEQVR42u3BAQ0AAADCoPdPbQ43oAAAAAAAAAAOBgYQAAG9rZ0gAAAAAElFTkSuQmCC"
)


def _pw_exe():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return hits[0] if hits else None


def _require_browser():
    return os.environ.get("KGP_REQUIRE_BROWSER") == "1"


# ── 소스 계약(결정적) ────────────────────────────────────────────────
def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.146"


def test_amazon_gallery_size_token_bypasses_naturalwidth_guard():
    # 수리 서명: 크기 토큰 URL(hr!==src)은 naturalWidth 가드를 건너뛴다. 토큰 없는 고정크기에만 가드.
    assert "var hr = hiRes(src);" in EX
    assert "if (hr === src) {" in EX and "if ((nw && nw < 40) || (nh && nh < 40)) continue;" in EX
    # 판별은 승격 URL(hr)의 상품성으로.
    assert "if (isProductImg(hr)) uniqPush(out, seen, hr);" in EX


# ── 실브라우저 오너 재현 조건(38px 실로드 썸네일) — 수리 증빙 + 가드 판별 ──
def _amz_body(alt_items):
    return (
        "<!doctype html><meta charset=utf-8>"
        '<meta property="og:image" content="https://m.media-amazon.com/images/I/713q1zpatL._AC_SL1500_.jpg">'
        '<div id="productTitle">SUPERONE Widget</div>'
        '<div id="imgTagWrapperId"><img id="landingImage" src="https://m.media-amazon.com/images/I/713q1zpatL._AC_SX679_.jpg"'
        " data-a-dynamic-image='{\"https://m.media-amazon.com/images/I/713q1zpatL._AC_SL1500_.jpg\":[1500,1500]}'></div>"
        '<div id="altImages"><ul>' + alt_items + "</ul></div>"
        '<span class="a-price"><span class="a-offscreen">$24.69</span></span>'
    )


def _extract_amazon(alt_items, dp):
    from playwright.sync_api import sync_playwright
    url = f"https://www.amazon.com/dp/{dp}"
    with sync_playwright() as pw:
        o = {"executable_path": _pw_exe()}
        px = os.environ.get("HTTPS_PROXY")
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def h(r):
            u = r.request.url.split("#")[0]
            if u == url:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=_amz_body(alt_items))
            elif "media-amazon.com/images/" in u:   # 실 이미지 로드 → naturalWidth=38(옛 가드 발동 조건)
                r.fulfill(status=200, content_type="image/png", body=_PNG38)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        nat = page.evaluate("()=>[...document.querySelectorAll('#altImages img')].map(im=>im.naturalWidth)")
        b.close()
    return res, nat


@pytest.mark.skipif(not _pw_exe(), reason="Playwright/chromium 미설치")
def test_amazon_38px_thumbnails_collected_after_fix():
    # 오너 재현 조건: _AC_US40_ 썸네일 7장이 **실제 38px로 로드**(naturalWidth=38 → 옛 가드 발동).
    items = "".join(
        '<li class="item"><span class="a-button-thumbnail"><span class="a-button-text">'
        '<img alt="" src="https://m.media-amazon.com/images/I/71g%d._AC_US40_.jpg"></span></span></li>' % i
        for i in range(1, 8)
    )
    res, nat = _extract_amazon(items, "B0SUPERONE1")
    assert nat and nat[0] == 38, f"재현 조건 불충족: 썸네일이 38px로 로드되지 않음({nat[:3]})"
    imgs = res.get("images") or []
    assert len(imgs) >= 5, f"수리 실패: 38px 썸네일 갤러리 병합 안 됨(수집 {len(imgs)}장)"   # 1 → n
    assert len(imgs) >= 8   # 대표 + 썸네일 7


@pytest.mark.skipif(not _pw_exe(), reason="Playwright/chromium 미설치")
def test_naturalwidth_guard_still_drops_tokenless_tiny_icons():
    # 판별 증빙(가드 미제거): 크기 토큰 **없는** 38px 이미지(진짜 아이콘류)는 여전히 배제된다.
    #   → 수리가 가드를 통째로 없앤 게 아니라 '토큰 있는 정품 썸네일'만 통과시킨다(오탐 0 유지).
    items = (
        '<li class="item"><span class="a-button-thumbnail"><span class="a-button-text">'
        '<img alt="" src="https://m.media-amazon.com/images/G/01/icon-plain.png"></span></span></li>'
    )
    res, nat = _extract_amazon(items, "B0ICONONLY1")
    assert nat and nat[0] == 38
    imgs = res.get("images") or []
    # 토큰 없는 38px(hr===src) → 가드로 배제. 대표(landingImage, data-a-dynamic-image=1500px)만 생존.
    assert all("icon-plain" not in u for u in imgs), f"토큰 없는 아이콘이 새어들어옴: {imgs}"
