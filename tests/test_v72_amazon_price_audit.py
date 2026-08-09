"""tests/test_v72_amazon_price_audit.py — v72 STEP3: 아마존 가격 "-" 감사.

증상: 아마존 2건 가격 "-". 감사 결과: 호버 단건 수집이 목록 카드 가격/제목은 1차로 담지만(meta),
**보강 큐에 자동 등록을 안 해** 목록가 없는 카드('See options' 변형)가 "-"로 남음. 수리: kgpQuickCollect가
성공 시 enrichTargets로 보강 큐 자동 등록(벌크 경로와 동일). + amazon-search 픽스처로 목록 카드 가격 추출 검증.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
FIX = Path("fixtures/realpages/synthetic-amazon-search.html")


# ── source-contract: 호버 단건 → 보강 큐 자동 등록 ──
def test_hover_collect_enqueues_enrich():
    seg = CS.split("function kgpQuickCollect")[1].split("function kgpMarkExisting")[0]
    # 목록 카드 가격/제목 1차 전송(meta).
    #   v86-F: 페이로드가 `_kgpTileMeta` 단일 헬퍼로 빠졌다(단건·벌크 공유). 계약은 "타일 가격이
    #   실려 나가는가"이므로 헬퍼 정의에서 확인하고, 호출부는 헬퍼 경유만 본다(리터럴 고정 해제).
    assert "_kgpTileMeta(card)" in seg, "호버 수집이 타일 페이로드 헬퍼를 안 쓴다"
    _tile = CS.split("function _kgpTileMeta(", 1)[1].split("\n}", 1)[0]
    assert "price: c.price" in _tile and "currency: c.currency" in _tile, \
        "타일 페이로드에 목록 가격/통화가 안 실린다"
    # 성공 시 enrichTargets로 보강 큐 자동 등록(enrichStart).
    assert "resp.enrichTargets" in seg
    assert 'action: "enrichStart"' in seg


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))


_CHROME_STUB = """
window.chrome = {
  runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u, lastError: null },
  storage: {
    local: { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } },
    sync:  { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } }
  }
};
"""


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_amazon_search_card_price_extraction():
    """amazon-search 픽스처: .a-price 카드는 가격 추출($29.99/$14.50), 가격 없는 카드는 빈 가격(보강 대상)."""
    from playwright.sync_api import sync_playwright

    url = "https://www.amazon.com/s?k=wireless+charger"
    html = FIX.read_text(encoding="utf-8")
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()
        page.add_init_script(_CHROME_STUB)

        def handler(route):
            if route.request.url.split("#")[0] == url:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(url, wait_until="domcontentloaded")
        page.evaluate("(cs)=>{ (0,eval)(cs); }", CS)
        cards = page.evaluate(
            "() => (kgpFindCards()||[]).map(c => ({url:c.url, price:c.price, currency:c.currency, title:c.title}))"
        )
        b.close()
    by = {}
    for c in cards:
        for asin in ("B00PRICE01", "B00PRICE02", "B00NOPRIC1"):
            if asin in (c.get("url") or ""):
                by[asin] = c
    # 가격 있는 카드 2건 추출.
    assert by.get("B00PRICE01", {}).get("price") == "29.99", cards
    assert by.get("B00PRICE02", {}).get("price") == "14.50", cards
    # 가격 없는 카드도 카드로 인식(제목 있음) — 목록가 없음 → 보강으로 채움(호버가 enrich 등록).
    assert "B00NOPRIC1" in by, cards
    assert (by["B00NOPRIC1"].get("price") or "") == "", by["B00NOPRIC1"]
