"""tests/test_p5_woocommerce.py — P5 WooCommerce 어댑터 **편입만**(신규 구현 0).

자사몰이라 마켓 심사 4지점(고시·배송 enum·필수 옵션·리프 카테고리)이 없다. 그래서 이 트랙은
'정본 확보'가 아니라 **기존 배선 재사용 + 게이트 동형**이 전부다.

계약:
  1. 등록은 기존 `UploadDispatcher`(파일럿과 같은 경로)로만 — 새 HTTP 클라이언트 0.
  2. 페이로드 모양이 파일럿 `register_pilot_rows`와 동형(무재고 구매대행) + **draft** 안전판.
  3. 카나리·승인·중복 게이트가 쿠팡/스스와 동형. 계정 축 혼입 차단.
  4. 중복 판정은 **마켓별** — 대장 + WC 실조회(SKU).
  5. 고시류(쿠팡 전용)는 WC 페이로드에 싣지 않는다(무관 필드 생략 정합).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline import register_adapters as RA


def test_adapter_registered_and_canon_ready():
    ad = RA.get_adapter("woocommerce")
    assert ad is not None and ad.market_ko.startswith("멀티샵")
    st = ad.canon_status()
    assert st["ready"] is True and st["gaps"] == []
    # 자사몰이라 4지점이 '해당 없음'임을 출처로 남긴다(빈 ok가 아니라 사유 있는 ok).
    for point in RA.CANON_POINTS:
        assert st["points"][point]["ok"] is True
        assert st["points"][point]["source"]


def test_wrong_account_axis_blocked():
    """쿠팡·스스 계정명이 들어오면 정직 차단(축 혼입 방지 — 스스 어댑터와 동형)."""
    ad = RA.get_adapter("woocommerce")
    for bad in ("gogane", "woojoo", "chezgoga", "gocosmos", ""):
        res = ad.register({"title_ko": "x"}, bad)
        assert res["success"] is False and res["held"] is True
        assert "멀티샵 계정이 아닙니다" in res["error"]


def test_register_delegates_to_upload_dispatcher(monkeypatch):
    """① 신규 구현 0 — 기존 디스패처에 위임하고 결과만 매핑한다."""
    from src.seller_console import views as V
    seen = {}

    class _R:
        market, success, external_id, external_url, message = "woocommerce", True, "9911", "https://shop/p/9911", ""

    class _D:
        def dispatch(self, pd, markets):
            seen["pd"], seen["markets"] = pd, markets
            return type("DR", (), {"results": [_R()]})()

    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _D())
    out = RA.get_adapter("woocommerce").register(
        {"title_ko": "Fellow Stagg 주전자", "sell_price_krw": 894000, "sku": "B0GS4698H2",
         "images": ["https://x/1.jpg"], "description_html": "<p>상세</p>",
         "url": "https://www.amazon.de/dp/B0GS4698H2"}, "multishop")
    assert seen["markets"] == ["woocommerce"]
    assert out["success"] is True and out["product_id"] == "9911"
    assert out["url"] == "https://shop/p/9911" and out["sku"] == "B0GS4698H2"


def test_payload_matches_pilot_shape(monkeypatch):
    """② 파일럿과 **동형 페이로드** + draft 안전판. 무재고 구매대행(재고관리 off·instock·simple)."""
    from src.seller_console import views as V
    seen = {}

    class _D:
        def dispatch(self, pd, markets):
            seen.update(pd)
            return type("DR", (), {"results": []})()

    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _D())
    RA.get_adapter("woocommerce").register(
        {"title_ko": "t", "sell_price_krw": 1000, "sku": "S1", "images": ["i"],
         "description_html": "d", "url": "https://a/dp/S1"}, "multishop")
    assert seen["status"] == "draft"                     # 파일럿과 같은 안전판
    assert seen["manage_stock"] is False
    assert seen["stock_status"] == "instock"
    assert seen["product_type"] == "simple"
    assert seen["sku"] == "S1"                           # 파일럿과 다른 점(중복 판정 근거)
    # ⑤ 쿠팡 전용 고시류는 WC와 무관 — 싣지 않는다.
    for coupang_only in ("notices", "origin", "certifications", "return_center_code"):
        assert coupang_only not in seen


def test_source_meta_recorded(monkeypatch):
    """출처 메타(_kgp_source_sku/url)를 남긴다 — 다음 실행·백필이 상품을 되짚을 수 있게."""
    from src.seller_console import views as V

    class _D:
        def dispatch(self, pd, markets):
            _D.pd = pd
            return type("DR", (), {"results": []})()

    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _D())
    RA.get_adapter("woocommerce").register(
        {"title_ko": "t", "sell_price_krw": 1, "sku": "S9", "url": "https://a/dp/S9"}, "multishop")
    keys = {m["key"]: m["value"] for m in _D.pd["pilot_meta"]}
    assert keys["_kgp_source_sku"] == "S9"
    assert keys["_kgp_source_url"] == "https://a/dp/S9"


def test_dispatcher_failure_is_honest(monkeypatch):
    """조용한 실패 0 — 디스패처 실패 사유가 그대로 올라온다."""
    from src.seller_console import views as V

    class _R:
        market, success, message, hint = "woocommerce", False, "WC 401: 자격 오류", "WC_KEY 확인"

    class _D:
        def dispatch(self, pd, markets):
            return type("DR", (), {"results": [_R()]})()

    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _D())
    out = RA.get_adapter("woocommerce").register({"title_ko": "t", "sku": "S"}, "multishop")
    assert out["success"] is False and "WC 401" in out["error"]

    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: None)
    out2 = RA.get_adapter("woocommerce").register({"title_ko": "t", "sku": "S"}, "multishop")
    assert out2["success"] is False and "디스패처" in out2["error"]


def test_duplicate_lookup_ledger_then_wc(monkeypatch):
    """④ 중복 판정 = 대장 우선 → 없으면 **WC 실조회**(SKU). 수동/타 경로 등록분도 잡는다."""
    from src.seller_console import views as V
    monkeypatch.setattr(V, "_lookup_registration", lambda sku, acct, marketplace=None: None)
    monkeypatch.setattr("src.vendors.woocommerce_client._find_by_sku",
                        lambda sku: {"id": 777, "status": "draft"} if sku == "S1" else None)
    hit = V._woocommerce_lookup("S1", "multishop")
    assert hit["product_id"] == "777" and hit["source"] == "woocommerce"
    assert V._woocommerce_lookup("S2", "multishop") is None
    assert V._woocommerce_lookup("", "multishop") is None          # 빈 SKU로 전체 첫 상품 오매칭 금지


def test_duplicate_lookup_survives_wc_outage(monkeypatch):
    """조회 실패가 등록을 막지 않는다(가용성 우선) — 단, 조용히 성공으로 위장하지도 않는다."""
    from src.seller_console import views as V
    monkeypatch.setattr(V, "_lookup_registration", lambda sku, acct, marketplace=None: None)
    monkeypatch.setattr("src.vendors.woocommerce_client._find_by_sku",
                        lambda sku: (_ for _ in ()).throw(RuntimeError("WC 500")))
    assert V._woocommerce_lookup("S1", "multishop") is None


def test_route_wires_market_and_lookup():
    """③ 라우트가 마켓별 기본 계정·중복 판정을 분기한다(대장은 마켓별 적재)."""
    src = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert '"woocommerce": "multishop"' in src
    assert "_woocommerce_lookup if market == \"woocommerce\"" in src
    assert 'marketplace=market' in src                    # 대장 적재도 마켓별


def test_template_offers_multishop():
    """화면: 마켓 select에 멀티샵 + 단일 계정 + 심사 없음 안내(정직)."""
    html = Path("src/seller_console/templates/register_pipe.html").read_text(encoding="utf-8")
    assert '<option value="woocommerce">멀티샵(자사몰)</option>' in html
    assert "woocommerce: [['multishop', '코가네멀티샵']]" in html
    assert "자사몰이라 심사가 없습니다" in html and "임시저장(draft)" in html
    # 디자인 규율: 하드코딩 hex·이모지 0(우리 토큰/아이콘셋만).
    import re as _re
    assert not _re.search(r"#[0-9a-fA-F]{6}", html)


def test_pilot_rows_carry_no_sku_so_they_are_undetectable():
    """**실측 사실 고정**: 파일럿 47건은 SKU 없이 등록돼 SKU 조회로 안 잡힌다.

    이 계약은 '못 잡는다'를 못박아 둔다 — 나중에 '잡히는 줄 알았다'는 오해를 막고,
    백필(파일럿 상품에 `_kgp_source_sku` 부여)이 끝나면 이 테스트가 바뀌어야 한다는 신호가 된다.
    """
    from src.channel_sync._channel_bridge import to_collected
    pilot_pd = {"title_ko": "t", "sell_price_krw": 1, "images": ["i"], "description_html": "d",
                "url": "https://www.amazon.co.jp/dp/B0XXXX1234", "status": "draft",
                "pilot_meta": [{"key": "_kgp_pilot_sid", "value": "12345"}],
                "manage_stock": False, "stock_status": "instock", "product_type": "simple"}
    assert to_collected(pilot_pd).get("sku") == ""        # 파일럿 = SKU 없음
    assert to_collected({**pilot_pd, "sku": "B0XXXX1234"}).get("sku") == "B0XXXX1234"   # 우리 경로 = 있음
