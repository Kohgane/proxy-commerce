"""tests/test_origin_sources_p3b.py — ② brand_origin.json + ③ 아마존 상세 파서·specs 배선.

③ 실측이 ② 추정보다 우선해야 하므로 파서 수리가 필수. 실 아마존 스냅샷(픽스처)로 검증 — 네트워크 0.
"""
from __future__ import annotations

import glob
import pytest

from src.pipeline import register_pipe as RP
from src.collectors.universal_scraper import UniversalScraper, extract_amazon_pdp

_REAL = glob.glob("fixtures/realpages/diag/kgp-snapshot-www-amazon-com-Craighill*.html")


def _real_html():
    if not _REAL:
        pytest.skip("실 아마존 스냅샷 픽스처 없음")
    return open(_REAL[0], encoding="utf-8", errors="ignore").read()


# ── ③ 아마존 상세 파서(실 스냅샷) ────────────────────────────────────────────────
def test_amazon_pdp_extracts_title_brand_specs():
    o = extract_amazon_pdp(_real_html())
    assert "Summit Business Card Case" in o["title"]     # 기존: 'Subtotal' 오추출
    assert o["brand"] == "Craighill"                      # 기존: None
    assert len(o["specs"]) >= 10                          # 기존: 0개
    labels = {l.lower() for l, _ in o["specs"]}
    assert "brand" in labels and "material" in labels


def test_amazon_pdp_empty_on_non_pdp():
    # 검색 페이지/빈 HTML엔 productTitle이 없음 → 빈값(가짜 생성 0).
    o = extract_amazon_pdp("<html><body>no pdp</body></html>")
    assert o["title"] == "" and o["brand"] == "" and o["specs"] == []
    assert extract_amazon_pdp(None)["specs"] == []


def test_parse_html_fixes_title_brand_and_carries_specs():
    sp = UniversalScraper().parse_html(_real_html(), "https://www.amazon.com/dp/B0BWFFFZD4")
    assert "Summit Business Card Case" in (sp.title or "")
    assert sp.brand == "Craighill"
    assert len(getattr(sp, "specs", []) or []) >= 10


def test_specs_reach_draft_wiring():
    # ③ 배선: _scraped_to_draft가 specs를 draft로 나른다(기존엔 드롭 → 원산지 영원히 미검출).
    import src.seller_console.views as V
    sp = UniversalScraper().parse_html(_real_html(), "https://www.amazon.com/dp/B0BWFFFZD4")
    draft = V._scraped_to_draft(sp)
    assert len(draft.get("specs") or []) >= 10


def test_real_origin_beats_brand_inference():
    # 실측(specs Country of Origin) > 추정(brand_inferred) 층위 보장.
    import src.seller_console.views as V
    sp = UniversalScraper().parse_html(_real_html(), "https://www.amazon.com/dp/B0BWFFFZD4")
    draft = V._scraped_to_draft(sp)
    # 이 상품은 아마존이 원산지 미표기 → 브랜드 추정으로 내려감(Craighill=미국).
    o, src = RP.resolve_origin(draft, brand_country_fn=lambda b: "미국" if "craighill" in b.lower() else None)
    assert (o, src) == ("미국", "brand_inferred")
    # 스펙에 원산지가 있으면 실측이 이긴다.
    draft["specs"] = list(draft["specs"]) + [("Country of Origin", "Vietnam")]
    assert RP.resolve_origin(draft, brand_country_fn=lambda b: "미국") == ("Vietnam", "amazon_field")


# ── ② brand_origin.json ────────────────────────────────────────────────────────
def test_brand_origin_json_loads_and_skips_uncertain():
    m = RP.load_brand_country_map("data/brand_origin.json")
    assert m.get("torras") == "중국" and m.get("craighill") == "미국"
    assert m.get("fjallraven") == "스웨덴" and m.get("sonicware") == "일본"
    # country 비운 항목(불확실)은 로드 안 함 → 폴백으로 내려감.
    for uncertain in ("polar", "bosca", "ars", "seeker"):
        assert uncertain not in m, uncertain
    assert "_readme" not in m and "_README" not in m       # 메타 키 제외


def test_title_substring_match(monkeypatch):
    # 오너 승인: sourcing_map에 brand 필드 부재 → 제목 부분일치 매칭.
    RP._BRAND_COUNTRY_CACHE.update({"loaded": True, "map": {"torras": "중국", "craighill": "미국"}})
    try:
        o, src = RP.resolve_origin({"title": "무선충전 거치대 TORRAS 정품"})   # 첫 토큰 아님
        assert (o, src) == ("중국", "brand_inferred")
        # 4글자 미만 키는 부분일치 제외(오탐 방지) — 목록에 없으면 폴백.
        assert RP.resolve_origin({"title": "무명 케이스"})[1] == "fallback"
    finally:
        RP._BRAND_COUNTRY_CACHE.update({"loaded": False, "map": {}})


# ── 커버리지 실측(오너 검수표) ──────────────────────────────────────────────────
def test_origin_coverage_counts():
    bc = lambda b: "중국" if "torras" in b.lower() else None
    c = RP.origin_coverage(["TORRAS 케이스", "TORRAS 충전기", "무명 지갑", ""], brand_country_fn=bc)
    assert c["total"] == 3
    assert c["brand_inferred"] == 2 and c["fallback"] == 1
    assert c["by_country"] == {"중국": 2}
    assert c["brand_inferred_pct"] == pytest.approx(66.7, abs=0.2)


def test_coverage_route(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner"; s["user_email"] = "shanks8@hanmail.net"; s["user_role"] = "admin"
    r = c.get("/admin/origin-coverage?limit=200")
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] is True
    assert d["total"] > 0 and d["brand_inferred"] + d["fallback"] + d["none"] == d["total"]
    assert d["brand_map_size"] >= 10
