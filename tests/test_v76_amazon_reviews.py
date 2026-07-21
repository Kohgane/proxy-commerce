"""tests/test_v76_amazon_reviews.py — v76 STEP6: 아마존 리뷰(DOM 폴백, 존재분만).

증상(오너 하네 기준선): 리뷰가 초기 JSON-LD/state에 없으면(아마존 등) 리뷰 0. 수리: 페이지에 **이미 렌더된**
리뷰 섹션([data-hook=review] 등) 상위 텍스트를 읽는 DOM 폴백 `_domReviews`(추가 네트워크 요청 0·존재분만).
JSON 리뷰가 부족(<3)할 때만 병합·본문 중복 제거. 계약: rev≥3(본문 텍스트 존재). 다른 페이지 오검출 0.
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
    assert MANIFEST["version"] == "1.5.113"


# ── source-contract: DOM 리뷰 폴백 함수 + 독립 병합 + 추가요청 0 ──
def test_dom_reviews_source():
    assert "function _domReviews()" in EX
    assert '[data-hook="review"]' in EX
    assert '[data-hook="review-body"]' in EX
    # 초기 JSON 리뷰 부족(<3)할 때 독립 병합(본문 중복 제거).
    assert "if (reviews.length < 3) {" in EX
    assert "var dr = _domReviews();" in EX
    # 추가 네트워크 요청 없음(fetch/XHR 미사용) — _domReviews는 DOM만 읽음.
    seg = EX.split("function _domReviews()")[1].split("function _domDescription()")[0]
    assert "fetch(" not in seg and "XMLHttpRequest" not in seg
    # DOM 리뷰 = tier2(가짜 소스 날조 금지).
    assert '(reviews.length ? "tier2" : "none")' in EX


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
def test_amazon_reviews_dom_fallback():
    """실 kgp-extractor: 아마존 DOM 리뷰 3건(본문·평점·작성자) + tier2 + 갤러리/상세 불변."""
    res = _extract("https://www.amazon.com/dp/B0AMZDP0001", AMZ)
    revs = res.get("reviews") or []
    assert len(revs) >= 3, revs
    # 본문 텍스트 존재(빈 리뷰 금지).
    assert all((r.get("text") or "").strip() for r in revs), revs
    # 평점 파싱(1..5) + 작성자.
    assert any(r.get("rating") == "5.0" for r in revs), revs
    assert any(r.get("author") for r in revs), revs
    # 존재분만 — 본문에 페이지 내 실제 텍스트.
    assert any("충전" in (r.get("text") or "") for r in revs), revs
    # tier2(DOM) 소스 표기.
    assert res.get("field_sources", {}).get("reviews") == "tier2", res.get("field_sources")
    # 리뷰 폴백이 갤러리/상세 회귀 없음.
    assert len(res.get("images") or []) == 5, res.get("images")
    assert len(res.get("detail_images") or []) == 4, res.get("detail_images")


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_no_spurious_reviews_on_non_review_page():
    """리뷰 섹션 없는 페이지(테무·알리·라쿠텐)에서 오검출 0(추천/설명을 리뷰로 오인 금지)."""
    for name, url in [
        ("synthetic-temu-detail", "https://www.temu.com/kr/x-g-1.html"),
        ("ali-detail", "https://www.aliexpress.com/item/1005006620123.html"),
        ("rakuten-detail", "https://item.rakuten.co.jp/river-outdoor/chair-001/"),
    ]:
        body = Path(f"fixtures/realpages/{name}.html").read_text(encoding="utf-8")
        res = _extract(url, body)
        assert (res.get("reviews") or []) == [], (name, res.get("reviews"))
