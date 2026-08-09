"""tests/test_v58_extract_contract.py — v58 STEP1: 추출 회귀 계약(3사이트 title·price·images).

결론(v58 STEP1): 확장 추출(kgp-extractor+content_script)은 title·price·images가 3 사이트(일반몰 JSON-LD·
testpage og/meta·테무 state-json)에서 정상 — **회귀 없음**. 오너 '제목·가격·옵션 미수집'의 근원은 북마클릿
엔티티 SyntaxError(v59에서 수리). 이 테스트는 그 계약을 고정(회귀 시 즉시 실패)한다.

behavioral 테스트는 real Chromium(Playwright) 필요 → 미설치 CI에선 skip, 로컬 전체 스위트에서 게이트.
source-contract 테스트는 어디서나(추출 코드 경로 존재 보증).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def _playwright_ok() -> bool:
    try:
        import playwright  # noqa: F401
        import glob
        return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
    except Exception:
        return False


# ── source-contract: 추출 코드 경로 존재(어디서나) ──
def test_title_has_multi_tier_fallback():
    # v60 STEP1 / v65 STEP1: 제목 = 어댑터 → Tier1(JSON) → 본문 h1(UI 제외) → og → document.title,
    #   순수 사이트명(_isBareSiteName)은 후보에서 배제하며 첫 유효값 채택.
    assert 's: "adapter"' in EX and 's: "tier1"' in EX and 's: "tier2"' in EX and 's: "tier3"' in EX
    assert "_isBareSiteName" in EX
    assert "_cleanH1" in EX and '_meta("og:title")' in EX


def test_price_has_jsonld_state_dom_paths():
    assert "_domPrice" in EX and "skuPrice" in EX             # DOM + sku(JSON) 가격
    assert "offers" in EX or "priceCurrency" in EX            # JSON-LD offers
    assert "_priceSanity" in EX                               # sanity 게이트


def test_images_gallery_paths():
    assert "_domImages" in EX and "gallery_images" in EX
    assert "IMG_KEY" in EX                                    # JSON 이미지 배열 키


# ── behavioral: real Chromium 3사이트 계약 ──
@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/Chromium 미설치(로컬 게이트 전용)")
def test_three_site_title_price_images_contract():
    spec = importlib.util.spec_from_file_location("dc", "scripts/_devshot_extract_contract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    res = mod.run()
    # 3사이트 모두 title·price 채움(비면 회귀). images는 픽스처에 있으면 ≥1.
    assert set(res.keys()) == set(mod.FIXTURES.keys()), "3 사이트 전부 실행"
    for site, r in res.items():
        assert r["title"] and len(r["title"]) >= 2, f"{site}: 제목 미수집(회귀)"
        assert r["price"] and str(r["price"]).strip() not in ("", "0"), f"{site}: 가격 미수집(회귀)"
        assert r["currency"] == "KRW", f"{site}: 통화 KRW 아님({r['currency']})"
        assert r["images"] >= 1, f"{site}: 이미지 미수집({r['images']})"
