"""tests/test_v78_review_meta.py — v78 STEP2: 리뷰 메타 수리.

실기기 진단: 테무 reviews:8·rating:"1"·review_count:"0" / 아마존 reviews:9·rating 없음 — 리뷰 메타 오매핑.
수리: rating은 (1,5]만 채택(0·1 더미 금지)·아니면 없음(정직), review_count는 실 리뷰 수 이상(스테일 0 보정).
계약: reviews>0이면 rating 1.0~5.0 또는 없음(0·1 더미 금지), review_count >= reviews.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
DUMMY = Path("fixtures/realpages/temu-review-dummy.html").read_text(encoding="utf-8")
AMZ = Path("fixtures/realpages/synthetic-amazon-dp.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.119"


# ── source-contract: 평점 (1,5] 관문 + review_count 바닥 보정 ──
def test_review_meta_source():
    # 상태 워크 rating은 (1,5]만(더미 0·1 skip).
    assert "if (rn > 1 && rn <= 5) res.rating = String(v);" in EX
    # 최종 정직화: rating (1,5] 아니면 '', review_count >= reviews.length.
    assert "if (!(_rn > 1 && _rn <= 5)) rating = \"\";" in EX
    assert "if (_cn < reviews.length) _cn = reviews.length;" in EX


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
def test_temu_dummy_rating_and_count_fixed():
    """테무 더미(score:1·review_count:0·리뷰 8건): rating은 더미 1/0 아님(1<r<=5), review_count>=8."""
    res = _extract("https://www.temu.com/kr/cat-review-g-1.html", DUMMY)
    revs = res.get("reviews") or []
    assert len(revs) >= 8, revs
    rating = (res.get("rating") or "").strip()
    # 계약: rating 더미(0·1) 금지 — 있으면 (1,5].
    assert rating not in ("0", "1"), ("더미 rating 저장!", rating)
    if rating:
        assert 1.0 < float(rating) <= 5.0, rating
    # review_count >= 실제 리뷰 수(스테일 0 보정).
    rc = (res.get("review_count") or "").strip()
    assert rc and int(rc) >= len(revs), ("review_count < 리뷰 수(스테일)!", rc, len(revs))


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_amazon_reviews_meta_honest():
    """아마존(DOM 리뷰): rating은 없음 또는 (1,5], review_count는 있으면 >= 리뷰 수(가짜 메타 0)."""
    res = _extract("https://www.amazon.com/dp/B0AMZDP0001", AMZ)
    revs = res.get("reviews") or []
    assert len(revs) >= 3, revs
    rating = (res.get("rating") or "").strip()
    assert rating not in ("0", "1"), ("더미 rating!", rating)
    if rating:
        assert 1.0 < float(rating) <= 5.0, rating
    rc = (res.get("review_count") or "").strip()
    if rc:
        assert int(rc) >= len(revs), (rc, len(revs))
