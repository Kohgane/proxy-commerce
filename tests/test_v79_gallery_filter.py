"""tests/test_v79_gallery_filter.py — v79 STEP4: 갤러리 오염 필터.

오너 진단(1.5.108) 갤러리 오염:
 · 테무: kwcdn 배너·쿠폰(material-put·upload_aimg) 꼬리 8장이 갤러리에 혼입.
 · 라쿠텐: 타상품 추천·리뷰 별점 gif·배너 혼입.
 · 알리: 80x80 썸네일 변형이 원본과 별개로 중복.
수리: ① _galleryScopeHost(host별) — 테무 kwcdn '/product/'만(material/aimg 배너 제외), 라쿠텐 현재 shop
        슬러그 밖 CDN 이미지 제외. ② hiRes가 알리 '.jpg_80x80xz.jpg' 썸네일 변형을 원본으로 정규화 → dedupe.
계약: 갤러리 내 배너·타상품 0.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.131"


# ── source-contract ──
def test_gallery_filter_source():
    assert "function _galleryScopeHost(list)" in EX
    assert "gallery = _galleryScopeHost(gallery);" in EX
    # 테무 kwcdn 배너·상품 경로.
    assert "material-put" in EX and "/product/" in EX and "kwcdn" in EX
    # 라쿠텐 shop 슬러그 스코프.
    assert "r10s\\.jp" in EX or "r10s.jp" in EX
    # 알리 썸네일 변형 정규화(hiRes).
    assert "v79 STEP4: 알리 썸네일 변형" in EX


# ── _galleryScopeHost 단위(node, mock location) ──
def _run_scope(host, pathname, urls):
    fn = re.search(r"function _galleryScopeHost\(list\) \{.*?\n  \}", EX, re.S).group(0)
    harness = (
        "var location={hostname:%s,pathname:%s};\n" % (json.dumps(host), json.dumps(pathname))
        + fn + "\n"
        + "process.stdout.write(JSON.stringify(_galleryScopeHost(%s))+'\\n');" % json.dumps(urls)
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node 미설치")
def test_temu_kwcdn_banner_excluded():
    urls = [
        "https://img.kwcdn.com/product/open/2024/main1.jpg",       # 상품(유지)
        "https://img.kwcdn.com/product/open/2024/main2.jpg",       # 상품(유지)
        "https://img.kwcdn.com/material-put/banner/coupon.jpg",    # 배너(제외)
        "https://img.kwcdn.com/upload_aimg/promo/event.jpg",       # 쿠폰(제외)
        "https://img.kwcdn.com/marketing/aimg/sale.png",           # 배너(제외)
        "https://other.cdn.com/x/real.jpg",                        # 비-kwcdn(유지)
    ]
    out = _run_scope("www.temu.com", "/kr/cat-g-1.html", urls)
    assert all("material-put" not in u and "upload_aimg" not in u and "/aimg" not in u for u in out), out
    assert "https://img.kwcdn.com/product/open/2024/main1.jpg" in out
    assert "https://other.cdn.com/x/real.jpg" in out
    assert len(out) == 3, out


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node 미설치")
def test_rakuten_other_shop_excluded():
    urls = [
        "https://tshop.r10s.jp/syuro/cabinet/main1.jpg",           # 현재 shop(유지)
        "https://tshop.r10s.jp/syuro/cabinet/main2.jpg",           # 현재 shop(유지)
        "https://tshop.r10s.jp/othershop/cabinet/rec.jpg",         # 타 shop 추천(제외)
        "https://image.rakuten.co.jp/otherstore/banner.jpg",       # 타상품 배너(제외)
        "https://cdn.example.com/generic.jpg",                     # 비-라쿠텐 CDN(유지)
    ]
    out = _run_scope("item.rakuten.co.jp", "/syuro/900037/", urls)
    assert not any("othershop" in u or "otherstore" in u for u in out), out
    assert "https://tshop.r10s.jp/syuro/cabinet/main1.jpg" in out
    assert "https://cdn.example.com/generic.jpg" in out
    assert len(out) == 3, out


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node 미설치")
def test_non_target_host_unaffected():
    urls = ["https://img.kwcdn.com/material-put/banner.jpg", "https://x.com/a.jpg"]
    out = _run_scope("www.amazon.com", "/dp/X", urls)
    assert out == urls, ("비대상 호스트는 무영향이어야", out)


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


# 알리 상세: 같은 원본의 80x80·640x640 썸네일 변형 + 원본 → 하나로 dedupe.
_ALI = (
    '<!doctype html><html><head><meta charset="utf-8"><title>Roller</title></head><body>'
    '<h1>Foam Roller</h1><div class="product-price">US $6.62</div>'
    '<div class="image-gallery-wrap">'
    '<img src="https://ae01.alicdn.com/kf/S1111.jpg_80x80xz.jpg" width="80" height="80">'
    '<img src="https://ae01.alicdn.com/kf/S1111.jpg_640x640q90.jpg" width="640" height="640">'
    '<img src="https://ae01.alicdn.com/kf/S1111.jpg" width="800" height="800">'
    '<img src="https://ae01.alicdn.com/kf/S2222.jpg_80x80xz.jpg" width="80" height="80">'
    '<img src="https://ae01.alicdn.com/kf/S2222.jpg" width="800" height="800">'
    '</div></body></html>'
)


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_ali_thumbnail_variants_deduped():
    """알리 80x80·640x640 썸네일 변형이 원본으로 정규화 → 원본 2장만(중복 0)."""
    from playwright.sync_api import sync_playwright
    url = "https://www.aliexpress.com/item/1005006620999.html"
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
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=_ALI)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()
    imgs = res.get("images") or []
    # 썸네일 변형 접미(_80x80·_640x640) 0.
    assert not any("_80x80" in u or "_640x640" in u for u in imgs), ("썸네일 변형 잔존!", imgs)
    # 원본 2장(S1111·S2222)만.
    assert "https://ae01.alicdn.com/kf/S1111.jpg" in imgs and "https://ae01.alicdn.com/kf/S2222.jpg" in imgs, imgs
    assert len([u for u in imgs if "alicdn" in u]) == 2, ("중복 dedupe 실패", imgs)
