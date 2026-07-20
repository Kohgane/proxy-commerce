"""tests/test_v76_detail_images.py — v76 STEP5: 상세이미지 일반화(아마존 경로 → 테무·알리·라쿠텐).

상세이미지(A+/설명/장식 영역)는 갤러리와 **별도 버킷**으로, needDom과 무관하게 독립 수집된다(v57/v71에서
구축). 본 STEP은 그 일반화를 **전 마켓 픽스처 계약**으로 못박는다: 아마존 #aplus·테무 decoration/richtext·
알리 description·라쿠텐 item-detail 상세이미지를 각각 수집 + 리뷰/추천 영역 제외 + 갤러리↔상세 상호배타.
확장 추출기 코드는 불변(순수 계약·하네스 인프라 추가) → manifest bump 없음.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
HARNESS = Path("tests/test_v70_realpage_harness.py").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_unchanged():
    # STEP5 자체는 추출기 코드 변경 없음(픽스처·하네스 계약만). 이후 STEP(리뷰 등)이 bump하므로 현재 핀 추적.
    assert MANIFEST["version"] == "1.5.105"


# ── 하네스가 상세이미지 계약을 지원(회귀 인프라) ──
def test_harness_supports_detail_images():
    assert "detail_images_min" in HARNESS
    assert "detail_images_exclude_substr" in HARNESS
    assert "갤러리·상세 중복" in HARNESS   # 갤러리↔상세 상호배타 가드


def test_detail_bucket_independent_of_needdom():
    # 상세이미지는 needDom과 무관하게 독립 수집(가격·갤러리 채워도 상세 시도) — 일반화의 핵심.
    assert "if (detailImages.length === 0) {" in EX
    assert "di2.detailImages" in EX


# ── 전 마켓 픽스처: 상세이미지 수집 + 스코프(리뷰/추천 제외) + 갤러리 상호배타 ──
_SITES = [
    ("synthetic-amazon-dp", "https://www.amazon.com/dp/B0AMZDP0001", 4, "REVIEWIMG"),
    ("synthetic-temu-detail", "https://www.temu.com/kr/x-g-1.html", 3, "temu-rec1"),
    ("ali-detail", "https://www.aliexpress.com/item/1005006620123.html", 2, None),
    ("rakuten-detail", "https://item.rakuten.co.jp/river-outdoor/chair-001/", 2, None),
]


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
            if r.request.url.split("#")[0].rstrip("/") == url.rstrip("/"):
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()
    return res


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
@pytest.mark.parametrize("name,url,dmin,excl", _SITES, ids=[s[0] for s in _SITES])
def test_detail_images_generalized(name, url, dmin, excl):
    """전 마켓: 상세이미지 dmin 이상 + 리뷰/추천 제외 + 갤러리↔상세 상호배타(같은 URL 중복 0)."""
    body = Path(f"fixtures/realpages/{name}.html").read_text(encoding="utf-8")
    res = _extract(url, body)
    det = res.get("detail_images") or []
    imgs = res.get("images") or []
    assert len(det) >= dmin, (name, len(det), det)
    if excl:
        assert not any(excl in u for u in det), (name, "리뷰/추천 상세 혼입", det)
    # 갤러리↔상세 상호배타.
    assert not (set(imgs) & set(det)), (name, "갤러리·상세 중복", set(imgs) & set(det))
    # desc_images 별칭도 동일(브리프 명명 분리).
    assert (res.get("desc_images") or []) == det, name
