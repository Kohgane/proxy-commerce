"""tests/test_v73_detection_harness.py — v73 STEP2: UI 감지 계층 순수 모듈 하네스 + CI 게이트.

kgp-detect.js(순수 모듈: document 입력 → {pageType, tiles, anchors} 출력)를 실 픽스처에 돌려 계약을
기계로 검증한다(chrome·주입 없음 → 무레이스). content_script는 이 모듈에 pageType 위임(단일 소스),
타일 규칙은 drift-guard로 byte-identical 못박음 → "감지 모듈 변경 시 전 픽스처 통과 필수"(추출은 되는데
버튼이 사라지는/타일을 놓치는 회귀를 CI가 잡는다).

계약(오너 확정 아마존 검색 기준치): pageType='list' · tiles=24 · main(유기)=16 · ad(스폰서)=8 ·
  asinMissing=0 · 각 tile anchor='img.s-image'(24/24) · countLabel='메인 16 · 광고 8'.
상세 3종: pageType='single'.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DETECT = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
import json
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
FIX = Path("fixtures/realpages")


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


# 순수 모듈 실행(chrome 불필요) — 픽스처 로드 → kgp-detect eval → detectUI(document, href).
_DETECT_CALL = """(a) => {
  const [detect] = a;
  (0, eval)(detect);
  return self.KGPDetect.detectUI(document, location.href);
}"""


def _detect(url, body):
    from playwright.sync_api import sync_playwright
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def handler(route):
            if route.request.url.split("#")[0] == url:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(url, wait_until="domcontentloaded")
        out = page.evaluate(_DETECT_CALL, [DETECT])
        b.close()
    return out


# ── 매니페스트: kgp-detect.js가 content_script.js 앞에 로드(위임 전제) ──
def test_manifest_loads_detect_before_content_script():
    assert MANIFEST["version"] == "1.5.98"
    bundles = [c.get("js", []) for c in MANIFEST["content_scripts"]]
    target = next((js for js in bundles if "content_script.js" in js), None)
    assert target is not None
    assert "kgp-detect.js" in target
    assert target.index("kgp-detect.js") < target.index("content_script.js")   # 로드 순서


# ── source-contract: content_script가 순수 모듈에 pageType 위임 ──
def test_content_script_delegates_pagetype():
    assert "KGPDetect.pageType(document, location.href" in CS
    assert 'typeof KGPDetect !== "undefined"' in CS


# ── drift-guard: 모듈 ⇔ content_script 감지 규칙 byte-identical(무단 분기 차단) ──
def test_detection_rules_no_drift():
    detail_body = r'(\/dp\/|\/gp\/product\/|\/vp\/products\/|item\.htm|aliexpress\.[^/]+\/item\/|[?&]goods_id=|[/-]g-\d{3,}|\/goods\/\d|\/product\/\d|\/products\/[\w-]+|\/itm\/)/i'
    list_body = r'(\/s\?|\/s\/|\/search|\/sch\b|[?&](q|keyword|query|search|k)=|\/category|\/categories|\/c\/|\/list\b|\/best\b|\/ranking|\/plp|\/browse|\/deals)/i'
    sponsored = '.s-sponsored-label-text, .puis-sponsored-label-text, [data-component-type="sp-sponsored-result"], [aria-label*="Sponsored"], [data-component-type="s-sponsored-label-info-icon"]'
    tile_sel = '[data-component-type="s-search-result"], div[data-asin]:not([data-asin=""])'
    asin = "/^[A-Z0-9]{10}$/"
    for token in (detail_body, list_body, sponsored, tile_sel, asin):
        assert token in CS, ("content_script에 없음", token)
        assert token in DETECT, ("kgp-detect에 없음", token)


# ── 계약: 아마존 검색 픽스처(순수 모듈 출력) ──
AMZ_SEARCH_URL = "https://www.amazon.com/s?k=ultraslim+phone+grip"


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_amazon_search_detection_contract():
    body = (FIX / "amazon-search.html").read_text(encoding="utf-8")
    d = _detect(AMZ_SEARCH_URL, body)
    assert d["pageType"] == "list", d                       # 목록
    assert d["tileCount"] == 24, d                          # tiles = 24
    assert d["main"] == 16, d                               # 유기(organic) = 16
    assert d["ad"] == 8, d                                  # 광고(sponsored) = 8
    assert d["asinMissing"] == 0, d                         # asin 결손 = 0
    assert len(d["anchors"]) == 24 and all(a == "img.s-image" for a in d["anchors"]), d  # 앵커 24/24
    assert d["countLabel"] == "메인 16 · 광고 8", d          # 벌크 카운트 표기


# ── 계약: 상세 3종 pageType='single' ──
DETAIL_CASES = [
    ("amazon-dp", "https://www.amazon.com/dp/B0AMZDP0001", "synthetic-amazon-dp.html"),
    ("temu", "https://www.temu.com/kr/goods.html?goods_id=601099", "synthetic-temu-detail.html"),
    ("yoshida-generic", "https://www.yoshidakaban.com/products/porter-tanker-01", "synthetic-generic-detail.html"),
]


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
@pytest.mark.parametrize("name,url,fixture", DETAIL_CASES, ids=[c[0] for c in DETAIL_CASES])
def test_detail_pagetype_single(name, url, fixture):
    body = (FIX / fixture).read_text(encoding="utf-8")
    d = _detect(url, body)
    assert d["pageType"] == "single", (name, d)             # 상세 = 단일(우측 단건 버튼 경로)
