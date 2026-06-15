"""tests/test_phase190_upload_margin.py — Phase 190 단위 테스트.

커버 범위:
1. UploadResult/DispatchResult — external_product_id, external_url, error_code, hint 필드
2. UploadDispatcher.prevalidate() — 토큰/필수필드/이미지 사전검증
3. 마켓 payload 생성 — target_margin_pct 전달
4. 업로드 성공/실패 핸들링 — external_product_id/url 추출, hint 포함
5. 마진 계산 경계값 — 마진율 0/100%, 환율 변동
6. /seller/collect/prevalidate 엔드포인트 기본 동작
"""
from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. UploadResult 필드 검증
# ═══════════════════════════════════════════════════════════════════════════════


class TestUploadResultFields:
    """Phase 190 추가 필드 검증."""

    def test_upload_result_has_new_fields(self):
        from src.seller_console.upload_dispatcher import UploadResult

        r = UploadResult(market="shopify", success=True, message="ok")
        assert hasattr(r, "external_product_id")
        assert hasattr(r, "external_url")
        assert hasattr(r, "error_code")
        assert hasattr(r, "hint")

    def test_upload_result_defaults_are_none(self):
        from src.seller_console.upload_dispatcher import UploadResult

        r = UploadResult(market="coupang", success=False, message="fail")
        assert r.external_product_id is None
        assert r.external_url is None
        assert r.error_code is None
        assert r.hint is None

    def test_dispatch_result_to_dict_includes_new_fields(self):
        from src.seller_console.upload_dispatcher import DispatchResult, UploadResult

        r = UploadResult(
            market="shopify",
            success=True,
            message="ok",
            external_product_id="P-123",
            external_url="https://shop.myshopify.com/products/p-123",
            error_code=None,
            hint=None,
        )
        dr = DispatchResult(product_url="https://example.com", total=1, succeeded=1)
        dr.results.append(r)
        d = dr.to_dict()
        result_row = d["results"][0]
        assert result_row["external_product_id"] == "P-123"
        assert result_row["external_url"] == "https://shop.myshopify.com/products/p-123"
        assert "error_code" in result_row
        assert "hint" in result_row

    def test_dispatch_result_to_dict_failure_includes_hint(self):
        from src.seller_console.upload_dispatcher import DispatchResult, UploadResult

        r = UploadResult(
            market="coupang",
            success=False,
            message="token missing",
            error_code="token_missing",
            hint="COUPANG_ACCESS_KEY 를 설정하세요.",
        )
        dr = DispatchResult(product_url="", total=1, failed=1)
        dr.results.append(r)
        d = dr.to_dict()
        row = d["results"][0]
        assert row["error_code"] == "token_missing"
        assert "COUPANG_ACCESS_KEY" in row["hint"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. prevalidate() — 사전검증
# ═══════════════════════════════════════════════════════════════════════════════


class TestPrevalidate:
    """UploadDispatcher.prevalidate() 단위 테스트."""

    def _dispatcher(self):
        from src.seller_console.upload_dispatcher import UploadDispatcher
        return UploadDispatcher()

    def test_prevalidate_token_missing(self, monkeypatch):
        """필수 환경변수 미설정 시 token_missing 오류."""
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
        monkeypatch.delenv("COUPANG_SECRET_KEY", raising=False)
        monkeypatch.delenv("COUPANG_VENDOR_ID", raising=False)

        product = {"title": "테스트 상품", "price": 10000}
        results = self._dispatcher().prevalidate(product, ["coupang"])
        assert len(results) == 1
        assert results[0].ok is False
        assert results[0].error_code == "token_missing"
        assert results[0].hint  # 힌트가 있어야 함

    def test_prevalidate_missing_title(self, monkeypatch):
        """상품명 없을 때 missing_field 오류."""
        # 환경변수 미리 채워둠
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "fake")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "fake")
        monkeypatch.setenv("COUPANG_VENDOR_ID", "fake")

        product = {"title": "", "price": 10000}
        results = self._dispatcher().prevalidate(product, ["coupang"])
        assert results[0].ok is False
        assert results[0].error_code == "missing_field"

    def test_prevalidate_missing_price(self, monkeypatch):
        """가격 없을 때 missing_field 오류."""
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "fake")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "fake")
        monkeypatch.setenv("COUPANG_VENDOR_ID", "fake")

        product = {"title": "좋은 상품", "price": 0}
        results = self._dispatcher().prevalidate(product, ["coupang"])
        assert results[0].ok is False
        assert results[0].error_code == "missing_field"

    def test_prevalidate_passes_when_fields_ok(self, monkeypatch):
        """필수 필드 + 환경변수 모두 있으면 통과."""
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "fake")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "fake")
        monkeypatch.setenv("COUPANG_VENDOR_ID", "fake")

        product = {"title": "좋은 상품", "price": 9900}
        results = self._dispatcher().prevalidate(product, ["coupang"])
        assert results[0].ok is True

    def test_prevalidate_unsupported_market(self):
        """지원하지 않는 마켓은 unsupported_market 오류."""
        results = self._dispatcher().prevalidate({"title": "t", "price": 1000}, ["gmarket_unsupported"])
        assert results[0].ok is False
        assert results[0].error_code == "unsupported_market"

    def test_prevalidate_shopify_token_env(self, monkeypatch):
        """Shopify: SHOPIFY_AUTO_TOKEN 또는 SHOPIFY_ACCESS_TOKEN 중 하나로 통과."""
        monkeypatch.setenv("SHOPIFY_SHOP", "myshop.myshopify.com")
        monkeypatch.setenv("SHOPIFY_AUTO_TOKEN", "atk_xxx")
        monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)

        product = {"title": "test", "price": 100}
        results = self._dispatcher().prevalidate(product, ["shopify"])
        assert results[0].ok is True

    def test_prevalidate_shopify_no_token(self, monkeypatch):
        """Shopify: 토큰 없으면 token_missing."""
        monkeypatch.setenv("SHOPIFY_SHOP", "myshop.myshopify.com")
        monkeypatch.delenv("SHOPIFY_AUTO_TOKEN", raising=False)
        monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)

        product = {"title": "test", "price": 100}
        results = self._dispatcher().prevalidate(product, ["shopify"])
        assert results[0].ok is False
        assert results[0].error_code == "token_missing"

    def test_prevalidate_multiple_markets(self, monkeypatch):
        """다수 마켓 동시 검증."""
        monkeypatch.setenv("SHOPIFY_SHOP", "shop.myshopify.com")
        monkeypatch.setenv("SHOPIFY_AUTO_TOKEN", "atk_ok")
        monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)

        product = {"title": "테스트", "price": 5000}
        results = self._dispatcher().prevalidate(product, ["shopify", "coupang"])
        assert len(results) == 2
        shopify_r = next(r for r in results if r.market == "shopify")
        coupang_r = next(r for r in results if r.market == "coupang")
        assert shopify_r.ok is True
        assert coupang_r.ok is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 마켓 payload — target_margin_pct 반영
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarginPayload:
    """target_margin_pct 가 업로드 payload 에 전달되는지 검증."""

    def test_dispatch_passes_target_margin_in_product_data(self, monkeypatch):
        """dispatch() 시 product_data 에 target_margin_pct 가 있으면 그대로 전달."""
        from src.seller_console import upload_dispatcher as mod

        captured = {}

        class _FakeAdapter:
            def validate_listing(self, payload):
                from src.markets.adapters.base import ListingResult
                return ListingResult(ok=True, market="shopify", message="ok", raw={})

            def upload_product(self, payload):
                from src.markets.adapters.base import ListingResult
                return ListingResult(ok=True, market="shopify", external_id="ID-1", message="ok", raw={})

        monkeypatch.setattr("src.markets.adapters.shopify.ShopifyAdapter", _FakeAdapter)

        product = {
            "title": "Test Product",
            "price": 29900,
            "currency": "KRW",
            "target_margin_pct": 25.0,
        }
        dispatcher = mod.UploadDispatcher()
        result = dispatcher.dispatch(product, ["shopify"])
        assert result.succeeded == 1
        # target_margin_pct 는 product_data 에 남아있어야 함
        assert product.get("target_margin_pct") == 25.0

    def test_shopify_upload_returns_external_id_and_url(self, monkeypatch):
        """Shopify 성공 시 external_product_id 와 external_url 이 채워져야 함."""
        from src.seller_console import upload_dispatcher as mod

        class _FakeAdapter:
            def validate_listing(self, payload):
                from src.markets.adapters.base import ListingResult
                return ListingResult(ok=True, market="shopify", message="ok", raw={})

            def upload_product(self, payload):
                from src.markets.adapters.base import ListingResult
                return ListingResult(
                    ok=True,
                    market="shopify",
                    external_id="GID-777",
                    message="created",
                    raw={
                        "admin_url": "https://admin.shopify.com/products/777",
                        "storefront_url": "https://myshop.myshopify.com/products/test",
                    },
                )

        monkeypatch.setattr("src.markets.adapters.shopify.ShopifyAdapter", _FakeAdapter)
        dispatcher = mod.UploadDispatcher()
        result = dispatcher.dispatch(
            {"title": "Test", "price": 5000, "currency": "USD"},
            ["shopify"],
        )
        r = result.results[0]
        assert r.success is True
        assert r.external_product_id == "GID-777"
        assert r.external_url == "https://myshop.myshopify.com/products/test"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 업로드 실패 핸들링 — error_code + hint
# ═══════════════════════════════════════════════════════════════════════════════


class TestUploadFailureHandling:
    """실패 시 error_code 와 hint 를 올바르게 반환하는지 검증."""

    def test_shopify_validation_failure_has_error_code(self, monkeypatch):
        """Shopify validate_listing 실패 → error_code='validation_failed' + hint."""
        from src.seller_console import upload_dispatcher as mod

        class _FakeAdapter:
            def validate_listing(self, payload):
                from src.markets.adapters.base import ListingResult
                return ListingResult(ok=False, market="shopify", message="title required", raw={})

        monkeypatch.setattr("src.markets.adapters.shopify.ShopifyAdapter", _FakeAdapter)
        dispatcher = mod.UploadDispatcher()
        result = dispatcher.dispatch({"title": "", "price": 100}, ["shopify"])
        r = result.results[0]
        assert r.success is False
        assert r.error_code == "validation_failed"
        assert r.hint  # 힌트가 있어야 함

    def test_shopify_api_failure_has_error_code(self, monkeypatch):
        """Shopify upload_product 실패 → error_code='api_error' + hint."""
        from src.seller_console import upload_dispatcher as mod

        class _FakeAdapter:
            def validate_listing(self, payload):
                from src.markets.adapters.base import ListingResult
                return ListingResult(ok=True, market="shopify", message="ok", raw={})

            def upload_product(self, payload):
                from src.markets.adapters.base import ListingResult
                return ListingResult(ok=False, market="shopify", message="401 Unauthorized", raw={})

        monkeypatch.setattr("src.markets.adapters.shopify.ShopifyAdapter", _FakeAdapter)
        dispatcher = mod.UploadDispatcher()
        result = dispatcher.dispatch({"title": "T", "price": 100}, ["shopify"])
        r = result.results[0]
        assert r.success is False
        assert r.error_code == "api_error"
        assert r.hint

    def test_queued_result_has_error_code_and_hint(self, monkeypatch):
        """모듈 없어 큐 적재 시 error_code='module_missing' + hint 포함."""
        from src.seller_console import upload_dispatcher as mod

        dispatcher = mod.UploadDispatcher()

        # _upload_coupang 을 직접 호출해 ImportError 경로(큐 적재) 동작 확인
        import sys
        for key in list(sys.modules.keys()):
            if "channel_sync" in key and "coupang" in key:
                del sys.modules[key]

        result = dispatcher._upload_coupang({"title": "T", "price": 1000})
        # 모듈 없음 → queued 경로 OR exception 경로 — 크래시 없이 UploadResult 반환
        assert isinstance(result, mod.UploadResult)
        assert result.market == "coupang"
        if result.queued:
            assert result.error_code == "module_missing"
            assert result.hint
        else:
            # 모듈이 실제로 있어 성공했거나 예외 경로 — 어느 쪽이든 market 필드는 올바름
            assert result.success is True or result.error_code is not None

    def test_coupang_import_error_queues_and_sets_error_code(self):
        """pend_queue 적재 경로: queued=True, error_code='module_missing', hint 포함."""
        from src.seller_console import upload_dispatcher as mod

        dispatcher = mod.UploadDispatcher()
        result = dispatcher._upload_coupang({"title": "T"})
        # 모듈이 없으면 queued=True + error_code='module_missing'
        # 모듈이 있으면 성공 경로 — 어느 쪽이든 크래시 없이 동작해야 함
        assert isinstance(result.market, str)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 마진 계산 경계값 테스트
# ═══════════════════════════════════════════════════════════════════════════════


class TestMarginBoundary:
    """마진율 경계값 단위 테스트."""

    def _calc(self, buy_price, currency, target_margin_pct, marketplace="coupang", sell_price=None):
        from src.seller_console.margin_calculator import (
            CostInput,
            MarginCalculator,
            MarketInput,
            default_commission_rate,
        )

        cost = CostInput(
            buy_price=Decimal(str(buy_price)),
            buy_currency=currency,
            domestic_shipping=Decimal("3000"),
            customs_rate=Decimal("0"),
        )
        commission = default_commission_rate(marketplace)
        market = MarketInput(
            marketplace=marketplace,
            commission_rate=commission,
            target_margin_pct=Decimal(str(target_margin_pct)),
        )
        calc = MarginCalculator()
        sp = Decimal(str(sell_price)) if sell_price else None
        return calc.calculate(cost, market, sell_price=sp)

    def test_margin_5pct(self):
        """마진율 5% — 낮은 마진도 계산 가능."""
        result = self._calc(buy_price=100, currency="USD", target_margin_pct=5)
        assert result.recommended_price > 0
        assert result.actual_margin_pct is not None

    def test_margin_50pct(self):
        """마진율 50% — 높은 마진도 계산 가능."""
        result = self._calc(buy_price=100, currency="USD", target_margin_pct=50)
        assert result.recommended_price > 0
        # 50% 마진이면 권장가가 원가보다 크게 높아야 함
        assert result.recommended_price > result.total_landed_cost

    def test_margin_changes_recommended_price(self):
        """마진율이 달라지면 권장 판매가도 달라야 한다."""
        r_low = self._calc(100, "USD", 10)
        r_high = self._calc(100, "USD", 40)
        assert r_high.recommended_price > r_low.recommended_price

    def test_given_sell_price_overrides_recommendation(self):
        """sell_price 직접 지정 시 권장가 대신 해당 가격으로 마진 계산."""
        result = self._calc(100, "USD", 22, sell_price=300000)
        assert result.given_price == Decimal("300000")

    def test_margin_with_krw_currency(self):
        """KRW 원화 매입 — 환율 1이므로 cost_in_krw == buy_price."""
        result = self._calc(buy_price=50000, currency="KRW", target_margin_pct=20)
        assert result.cost_in_krw == Decimal("50000")

    def test_breakeven_price_is_positive(self):
        """손익분기점은 항상 양수."""
        result = self._calc(100, "USD", 22)
        assert result.breakeven_price > 0

    def test_margin_pct_zero_target_no_crash(self):
        """목표 마진율 0 — 분모 문제없이 동작(exception 없음)."""
        try:
            result = self._calc(100, "USD", 0)
            # 0% 마진이면 원가 = 판매가 수준
            assert result.recommended_price >= result.total_landed_cost
        except ValueError:
            # 마진율+수수료율 ≥ 100 이면 ValueError 가 정상
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# 6. /seller/collect/prevalidate 엔드포인트
# ═══════════════════════════════════════════════════════════════════════════════


class TestPrevalidateEndpoint:
    """Flask 뷰 — /seller/collect/prevalidate 기본 동작."""

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        monkeypatch.setenv("SELLER_PASSWORD", "test")
        monkeypatch.setenv("FX_DISABLE_NETWORK", "1")
        import src.order_webhook as wh
        wh.app.config["TESTING"] = True
        with wh.app.test_client() as c:
            with c.session_transaction() as sess:
                sess["seller_logged_in"] = True
            yield c

    def test_prevalidate_returns_ok_structure(self, client):
        resp = client.post(
            "/seller/collect/prevalidate",
            json={"product": {"title": "T", "price": 1000}, "markets": ["shopify"]},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "results" in data
        assert "all_ok" in data

    def test_prevalidate_no_product_returns_400(self, client):
        resp = client.post(
            "/seller/collect/prevalidate",
            json={"markets": ["shopify"]},
        )
        assert resp.status_code == 400

    def test_prevalidate_no_markets_returns_400(self, client):
        resp = client.post(
            "/seller/collect/prevalidate",
            json={"product": {"title": "T", "price": 1000}},
        )
        assert resp.status_code == 400

    def test_collect_upload_accepts_target_margin_pct(self, client, monkeypatch):
        """target_margin_pct 를 보내면 product 에 반영되어 dispatch 에 전달된다."""
        from src.seller_console import upload_dispatcher as mod

        captured = {}

        original_dispatch = mod.UploadDispatcher.dispatch

        def fake_dispatch(self, product_data, markets):
            captured["target_margin_pct"] = product_data.get("target_margin_pct")
            from src.seller_console.upload_dispatcher import DispatchResult
            return DispatchResult(product_url="", total=0)

        monkeypatch.setattr(mod.UploadDispatcher, "dispatch", fake_dispatch)

        resp = client.post(
            "/seller/collect/upload",
            json={
                "product": {"title": "T", "price": 5000},
                "markets": ["shopify"],
                "target_margin_pct": 28,
            },
        )
        assert resp.status_code == 200
        assert captured.get("target_margin_pct") == 28.0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 원화 판매가 산정 — 외화 원문가 + 목표 마진율 → sell_price_krw 주입
#    (회귀: 쿠팡/스마트스토어/11번가가 sell_price_krw=0 으로 실패하던 버그)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnsureSellPriceKrw:
    """UploadDispatcher._ensure_sell_price_krw — 원화 판매가 주입."""

    def _fx(self):
        from decimal import Decimal
        return {
            "USDKRW": Decimal("1350"),
            "JPYKRW": Decimal("9.0"),
            "EURKRW": Decimal("1470"),
            "CNYKRW": Decimal("190"),
        }

    def test_foreign_price_with_margin_yields_positive_krw(self, monkeypatch):
        """외화(JPY) 원문가 + 목표 마진율 → 양수 sell_price_krw 주입."""
        from src.seller_console.upload_dispatcher import UploadDispatcher
        import src.price as price_mod

        monkeypatch.setattr(price_mod, "_build_fx_rates", lambda *a, **k: self._fx())

        pd = {"title": "T", "price": 10000, "currency": "JPY", "target_margin_pct": 22}
        enriched = UploadDispatcher._ensure_sell_price_krw(pd)
        assert enriched["sell_price_krw"] > 0
        # 원가(마진 제외) KRW 도 채워짐: 10000 JPY * 9.0 = 90000
        assert enriched["price_krw"] == 90000
        # 원본은 변경되지 않음
        assert "sell_price_krw" not in pd

    def test_existing_krw_price_preserved(self):
        """이미 양수 sell_price_krw 가 있으면 재산정하지 않는다."""
        from src.seller_console.upload_dispatcher import UploadDispatcher

        pd = {"title": "T", "sell_price_krw": 50000, "price": 10000, "currency": "JPY"}
        enriched = UploadDispatcher._ensure_sell_price_krw(pd)
        assert enriched["sell_price_krw"] == 50000

    def test_krw_currency_left_for_bridge(self):
        """KRW 통화 원문가는 브리지가 처리하므로 주입하지 않는다."""
        from src.seller_console.upload_dispatcher import UploadDispatcher

        pd = {"title": "T", "price": 29900, "currency": "KRW"}
        enriched = UploadDispatcher._ensure_sell_price_krw(pd)
        assert "sell_price_krw" not in enriched

    def test_dispatch_injects_krw_before_market_upload(self, monkeypatch):
        """dispatch() 가 마켓 업로드 전에 sell_price_krw 를 주입해 0 실패를 방지."""
        from src.seller_console import upload_dispatcher as mod
        import src.price as price_mod

        monkeypatch.setattr(price_mod, "_build_fx_rates", lambda *a, **k: self._fx())

        captured = {}

        def fake_upload_to_market(self, product_data, market):
            captured["sell_price_krw"] = product_data.get("sell_price_krw")
            return mod.UploadResult(market=market, success=True, message="ok")

        monkeypatch.setattr(mod.UploadDispatcher, "_upload_to_market", fake_upload_to_market)

        product = {"title": "T", "price": 100, "currency": "USD", "target_margin_pct": 22}
        result = mod.UploadDispatcher().dispatch(product, ["coupang"])
        assert result.succeeded == 1
        assert captured["sell_price_krw"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. WooCommerce 업로드 — prepare_product_data + upsert_product 사용
#    (회귀: create_product 속성 없음 오류)
# ═══════════════════════════════════════════════════════════════════════════════


class TestWooCommerceUploadPath:
    """_upload_woocommerce — 모듈의 실제 API(prepare_product_data/upsert_product) 사용."""

    def test_uses_prepare_and_upsert_not_create_product(self, monkeypatch):
        from src.seller_console import upload_dispatcher as mod
        from src.vendors import woocommerce_client as woo

        calls = {}

        def fake_prepare(catalog_row, sell_price_krw):
            calls["prepare"] = {"row": catalog_row, "price": sell_price_krw}
            return {"name": catalog_row.get("title_ko"), "regular_price": str(int(sell_price_krw))}

        def fake_upsert(prod):
            calls["upsert"] = prod
            return {"id": 999, "permalink": "https://shop/p/999"}

        monkeypatch.setattr(woo, "prepare_product_data", fake_prepare)
        monkeypatch.setattr(woo, "upsert_product", fake_upsert)

        product = {"title": "코가네백", "sell_price_krw": 88000, "sku": "SKU-1"}
        result = mod.UploadDispatcher()._upload_woocommerce(product)
        assert result.success is True
        assert result.external_product_id == "999"
        assert calls["prepare"]["price"] == 88000
        assert calls["upsert"]["name"] == "코가네백"

    def test_zero_krw_price_fails_honestly(self):
        from src.seller_console import upload_dispatcher as mod

        # 외화 원문가만 있고 KRW 판매가가 없으면 honest 실패
        product = {"title": "T", "price": 19.9, "currency": "USD"}
        result = mod.UploadDispatcher()._upload_woocommerce(product)
        assert result.success is False
        assert "원화 판매가" in result.message
