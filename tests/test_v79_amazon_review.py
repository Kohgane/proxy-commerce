"""tests/test_v79_amazon_review.py — v79 STEP5: 아마존 리뷰 본문·평점.

오너 진단(1.5.108): 아마존 리뷰 text=author 복제(본문 셀렉터가 저자 프로필 노드 .a-profile-content를
먼저 잡음) + rating 필드 미매핑. 수리: 본문 셀렉터를 구체적 리뷰 본문만(저자 노드 배제)·순차 → text≠author
봉인. rating은 'X out of 5 stars'/class a-star-N에서 1.0~5.0만. 계약: text≠author, rating 1.0~5.0.
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
    assert MANIFEST["version"] == "1.5.116"


# ── source-contract ──
def test_review_source():
    assert "v79 STEP5: text≠author 봉인" in EX
    assert "if (t && t.length >= 3 && t !== author) { body = t; break; }" in EX
    assert "if (!body) continue;" in EX                          # 본문 없으면 저자 복제 저장 금지
    assert "be.closest(AUTH_SEL)" in EX                          # 저자 프로필 하위 배제
    assert "out of|\\/)\\s*5" in EX or "out of" in EX            # X out of 5 파싱
    # 넓은 [class*=content]·p 폴백 제거(저자 복제 근원).
    assert "[class*=\"content\" i],[class*=\"comment-text\" i],p'" not in EX


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


# 아마존 DP: 리뷰 카드 — 저자 프로필(.a-profile-content)이 본문보다 DOM 먼저(복제 유발 구조).
_AMZ = (
    '<!doctype html><html><head><meta charset="utf-8"><title>Steamer</title></head><body>'
    '<span id="productTitle">Handheld Garment Steamer</span>'
    '<div id="corePrice_desktop"><span class="a-price"><span class="a-offscreen">$25.99</span></span></div>'
    '<div id="cm-cr-dp-review-list">'
    # 리뷰 1: 저자 노드가 본문보다 앞.
    '<div data-hook="review" id="customer_review-R1">'
    '  <div class="a-profile"><div class="a-profile-content"><span class="a-profile-name">Jane D.</span></div></div>'
    '  <i data-hook="review-star-rating" class="a-icon a-star-5"><span class="a-icon-alt">5.0 out of 5 stars</span></i>'
    '  <span data-hook="review-body"><span>This steamer heats up fast and removes wrinkles easily. Highly recommend.</span></span>'
    '</div>'
    # 리뷰 2: 4점.
    '<div data-hook="review" id="customer_review-R2">'
    '  <div class="a-profile"><div class="a-profile-content"><span class="a-profile-name">Mark T.</span></div></div>'
    '  <i data-hook="review-star-rating" class="a-icon a-star-4"><span class="a-icon-alt">4.0 out of 5 stars</span></i>'
    '  <span data-hook="review-body"><span>Good value, compact for travel. Cord could be longer.</span></span>'
    '</div>'
    # 리뷰 3: 별점 class 폴백(a-icon-alt 없음).
    '<div data-hook="review" id="customer_review-R3">'
    '  <div class="a-profile"><div class="a-profile-content"><span class="a-profile-name">Sofia K.</span></div></div>'
    '  <i data-hook="review-star-rating" class="a-icon a-star-3"></i>'
    '  <span data-hook="review-body"><span>Works okay but takes a while to fill the water tank.</span></span>'
    '</div>'
    '</div>'
    '<div class="imgTagWrapper"><img src="https://m.media-amazon.com/images/I/71x.jpg" width="500" height="500"></div>'
    '</body></html>'
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
def test_amazon_review_text_not_author_and_rating():
    """리뷰 3건: text≠author(저자 복제 0)·본문 실제 내용·rating 5.0/4.0/3.0(1~5)."""
    res = _extract("https://www.amazon.com/dp/STEAMERV79", _AMZ)
    revs = res.get("reviews") or []
    assert len(revs) >= 3, revs
    authors = {"Jane D.", "Mark T.", "Sofia K."}
    for rv in revs:
        txt = (rv.get("text") or "").strip()
        au = (rv.get("author") or "").strip()
        assert txt, ("빈 본문", rv)
        assert txt != au, ("text=author 복제!", rv)
        assert txt not in authors, ("본문이 저자명!", rv)
        rt = (rv.get("rating") or "").strip()
        if rt:
            assert 1.0 <= float(rt) <= 5.0, ("rating 범위 밖", rt, rv)
    # 실제 본문·평점 매핑 확인('X out of 5' 원본 형식 보존).
    assert any("heats up fast" in (rv.get("text") or "") and (rv.get("rating") == "5.0") for rv in revs), revs
    assert any("Good value" in (rv.get("text") or "") and (rv.get("rating") == "4.0") for rv in revs), revs
    # class 폴백(a-star-3, a-icon-alt 없음) → 3점.
    assert any("water tank" in (rv.get("text") or "") and (rv.get("rating") == "3") for rv in revs), revs
