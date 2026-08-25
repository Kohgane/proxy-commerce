"""tests/test_register_adapters_p5.py — P5: 마켓 어댑터 인터페이스 + 정본 게이트.

쿠팡 관통이 확정한 것: 마켓별로 갈리는 지점은 **4개뿐**(고시정보·배송·옵션 필수값·카테고리 매핑).
그 4개를 인터페이스로 못박고, **정본이 없으면 전송을 막는다** — 쿠팡이 6차 왕복을 태운 이유가
"그럴듯한 기본값을 넣어 보낸 것"이었기 때문이다.

계약:
  1. 4지점이 인터페이스로 고정돼 있다.
  2. 쿠팡 = 정본 확보(출처 표기) → 게이트 통과.
  3. 스마트스토어 = **정본 미확보 → 등록 차단**(사유에 어느 지점인지 명시).
  4. WooCommerce = 편입만(신규 구현 0).
  5. 차단 시 마켓 API를 **호출하지 않는다**.
"""
from __future__ import annotations

import pytest

from src.pipeline import register_adapters as RA


def test_four_canon_points_are_the_interface():
    assert RA.CANON_POINTS == ("notice", "delivery", "options", "category")


def test_coupang_canon_ready_with_sources():
    st = RA.get_adapter("coupang").canon_status()
    assert st["ready"] is True and st["gaps"] == []
    # ok=True인 지점은 **출처**를 밝힌다(왜 ok인지 다음 세션이 되묻지 않게).
    for p in RA.CANON_POINTS:
        assert st["points"][p]["ok"] is True
        assert st["points"][p]["source"], p


def test_smartstore_blocked_until_canon_supplied():
    ad = RA.get_adapter("smartstore")
    st = ad.canon_status()
    assert st["ready"] is False
    assert set(st["gaps"]) == set(RA.CANON_POINTS)          # 4지점 전부 미확보
    for p in RA.CANON_POINTS:
        assert st["points"][p]["ok"] is False
        assert st["points"][p]["gap"], p                     # 미확보 '사유'가 있어야 한다


def test_smartstore_register_blocks_without_calling_api(monkeypatch):
    """차단은 전송 전에 — 네이버 API를 부르지 않는다(카나리 낭비 0)."""
    import src.uploaders.naver_uploader as NU
    monkeypatch.setattr(NU.NaverSmartStoreUploader, "upload_product",
                        lambda self, p: pytest.fail("정본 미확보인데 마켓 API 호출됨"))
    res = RA.get_adapter("smartstore").register({"title_ko": "x", "sell_price_krw": 10000}, "gogane")
    assert res["success"] is False and res["held"] is True
    assert "정본 미확보" in res["error"]
    assert set(res["canon_gaps"]) == set(RA.CANON_POINTS)


def test_smartstore_gap_reasons_cite_real_code_values():
    """미확보 사유는 **실제 코드에 있는 값**을 지목한다(막연한 '검증 필요' 금지)."""
    from pathlib import Path
    src = Path("src/uploaders/naver_uploader.py").read_text(encoding="utf-8")
    reasons = RA.SmartStoreAdapter.GAP_REASONS
    assert "0200037" in reasons["notice"] and "0200037" in src
    assert "DIRECT_DELIVERY" in reasons["delivery"] and "DIRECT_DELIVERY" in src
    assert "50000000" in reasons["category"] and "50000000" in src
    # 옵션: 필수 구매 옵션 배선이 실제로 없다(쿠팡 9차와 동형).
    assert "optionInfo" not in src


def test_woocommerce_is_enrollment_only():
    ad = RA.get_adapter("woocommerce")
    assert ad.canon_status()["ready"] is True                # 자사몰 — 마켓 심사 규격 자체가 없음
    res = ad.register({}, "gogane")
    assert res["success"] is False and res["held"] is True   # 신규 구현 0 — 파일럿 경로가 정본
    assert "파일럿" in res["error"]


def test_coupang_adapter_delegates_to_verified_uploader(monkeypatch):
    """쿠팡은 재구현하지 않는다 — 검증된 dispatch에 위임(정본 이원화 금지)."""
    import src.seller_console.views as V
    seen = {}
    monkeypatch.setattr(V, "_coupang_account_dispatch",
                        lambda pd, acct: seen.update({"pd": pd, "acct": acct}) or {"success": True})
    out = RA.get_adapter("coupang").register({"title_ko": "t"}, "woojoo")
    assert out["success"] is True and seen["acct"] == "woojoo"


def test_canon_report_lists_every_market():
    rep = RA.canon_report()
    assert set(rep) == {"coupang", "woocommerce", "smartstore"}
    assert rep["coupang"]["ready"] is True
    assert rep["smartstore"]["ready"] is False and rep["smartstore"]["note"]


def test_unknown_market_returns_none():
    assert RA.get_adapter("shopee") is None and RA.get_adapter("") is None
