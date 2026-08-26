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


def test_smartstore_canon_supplied_gate_opened():
    """정본(ss_upload.py)이 도착해 게이트가 열렸다 — 차단 상태는 해소됨(#671)."""
    st = RA.get_adapter("smartstore").canon_status()
    assert st["ready"] is True and st["gaps"] == []
    for p in RA.CANON_POINTS:
        assert st["points"][p]["ok"] is True and st["points"][p]["source"]
    # 승계받지 못한 조각은 숨기지 않고 partial로 남긴다(정직).
    assert st["partial"]["category"]


def test_canon_gate_still_blocks_an_unready_adapter():
    """게이트 **메커니즘**은 살아 있다 — 미확보 어댑터는 전송 전에 차단된다."""
    class _Unready(RA.MarketAdapter):
        market, market_ko = "testmarket", "테스트마켓"

        def canon_status(self):
            return {"ready": False, "gaps": ["delivery", "category"],
                    "points": {}, "note": "미승계"}

        def register(self, product_data, account):
            gate = self._canon_gate()
            if gate:
                return gate
            pytest.fail("미확보인데 전송 경로로 진입함")

    res = _Unready().register({"title_ko": "x"}, "acct")
    assert res["success"] is False and res["held"] is True
    assert "정본 미확보" in res["error"] and "배송" in res["error"] and "카테고리 매핑" in res["error"]
    assert res["canon_gaps"] == ["delivery", "category"]


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
    assert rep["smartstore"]["ready"] is True and rep["smartstore"]["note"]


def test_unknown_market_returns_none():
    assert RA.get_adapter("shopee") is None and RA.get_adapter("") is None
