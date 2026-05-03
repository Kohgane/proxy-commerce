"""tests/test_seller_pricing_views.py — 셀러 마진 계산기 뷰 테스트 (Phase 125).

테스트 범위:
  - GET /seller/pricing → 200
  - POST /seller/pricing/calc → 200, JSON 스키마 검증
  - POST /seller/pricing/compare → 200, 응답 list
  - POST /api/v1/pricing/calculate → 200
"""
from __future__ import annotations

import sys
import os
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """셀러 콘솔이 등록된 Flask 앱 테스트 클라이언트."""
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GET /seller/pricing
# ---------------------------------------------------------------------------

class TestPricingPage:
    def test_pricing_page_returns_200(self, client):
        """GET /seller/pricing → 200."""
        resp = client.get("/seller/pricing")
        assert resp.status_code == 200

    def test_pricing_page_contains_compare_endpoint(self, client):
        """GET /seller/pricing 페이지에 /seller/pricing/compare 참조 포함."""
        resp = client.get("/seller/pricing")
        assert b"pricing/compare" in resp.data


# ---------------------------------------------------------------------------
# POST /seller/pricing/calc
# ---------------------------------------------------------------------------

class TestPricingCalc:
    def _post(self, client, payload):
        return client.post(
            "/seller/pricing/calc",
            json=payload,
            content_type="application/json",
        )

    def test_calc_krw_coupang_22pct(self, client):
        """KRW 매입 + 쿠팡 + 22% 목표 마진 → 권장 판매가 및 실마진 반환."""
        resp = self._post(client, {
            "buy_price": 50000,
            "currency": "KRW",
            "marketplace": "coupang",
            "customs_rate": 0,
            "domestic_shipping": 3000,
            "target_margin_pct": 22,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        result = data["result"]
        assert result["recommended_price"] > 0
        assert "actual_margin_pct" in result
        assert "breakeven_price" in result

    def test_calc_usd_buy_price_converts(self, client):
        """USD 100 매입 → KRW 환산값이 0보다 큰지 확인."""
        resp = self._post(client, {
            "buy_price": 100,
            "currency": "USD",
            "marketplace": "smartstore",
            "customs_rate": 20,
            "target_margin_pct": 22,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["result"]["cost_in_krw"] > 0

    def test_calc_customs_threshold_over(self, client):
        """매입가가 면세 임계 초과 → 관세 금액 > 0."""
        resp = self._post(client, {
            "buy_price": 300000,
            "currency": "KRW",
            "marketplace": "coupang",
            "customs_rate": 20,
            "target_margin_pct": 22,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["result"]["customs_in_krw"] > 0

    def test_calc_customs_threshold_under(self, client):
        """매입가가 면세 임계 미달 → 관세 금액 = 0."""
        resp = self._post(client, {
            "buy_price": 100000,
            "currency": "KRW",
            "marketplace": "coupang",
            "customs_rate": 20,
            "target_margin_pct": 22,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["result"]["customs_in_krw"] == 0

    def test_calc_zero_price_returns_400(self, client):
        """매입가 0 → 400."""
        resp = self._post(client, {"buy_price": 0, "currency": "USD"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_calc_invalid_input_returns_400(self, client):
        """잘못된 입력 → 400."""
        resp = self._post(client, {"buy_price": "not_a_number"})
        assert resp.status_code == 400

    def test_calc_backward_compat_market_fee_rate(self, client):
        """기존 market_fee_rate 파라미터 하위 호환 동작."""
        resp = self._post(client, {
            "buy_price": 50000,
            "currency": "KRW",
            "market_fee_rate": 10.8,
            "target_margin_pct": 22,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

    def test_calc_response_schema(self, client):
        """응답에 필수 필드 모두 포함."""
        resp = self._post(client, {
            "buy_price": 100,
            "currency": "USD",
            "marketplace": "coupang",
            "customs_rate": 20,
            "target_margin_pct": 22,
        })
        assert resp.status_code == 200
        result = resp.get_json()["result"]
        required_fields = [
            "marketplace", "recommended_price", "actual_margin_krw",
            "actual_margin_pct", "breakeven_price", "total_landed_cost",
            "cost_in_krw", "customs_in_krw",
        ]
        for field in required_fields:
            assert field in result, f"필드 누락: {field}"


# ---------------------------------------------------------------------------
# POST /seller/pricing/compare
# ---------------------------------------------------------------------------

class TestPricingCompare:
    def _post(self, client, payload):
        return client.post(
            "/seller/pricing/compare",
            json=payload,
            content_type="application/json",
        )

    def test_compare_four_markets(self, client):
        """4개 마켓 비교 → 4개 결과 반환."""
        resp = self._post(client, {
            "buy_price": 100,
            "currency": "USD",
            "customs_rate": 20,
            "domestic_shipping": 3000,
            "target_margin_pct": 22,
            "marketplaces": ["coupang", "smartstore", "11st", "kohganemultishop"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert len(data["results"]) == 4

    def test_compare_default_marketplaces(self, client):
        """marketplaces 미지정 → 기본 4개 마켓."""
        resp = self._post(client, {
            "buy_price": 100,
            "currency": "USD",
            "customs_rate": 20,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert len(data["results"]) == 4

    def test_compare_results_have_marketplace_field(self, client):
        """각 결과에 marketplace 필드 포함."""
        resp = self._post(client, {
            "buy_price": 100,
            "currency": "USD",
            "customs_rate": 0,
            "marketplaces": ["coupang", "smartstore"],
        })
        assert resp.status_code == 200
        results = resp.get_json()["results"]
        mp_ids = {r["marketplace"] for r in results}
        assert "coupang" in mp_ids
        assert "smartstore" in mp_ids

    def test_compare_commission_rates_differ(self, client):
        """마켓별 수수료율이 다르므로 권장 판매가가 달라야 함."""
        resp = self._post(client, {
            "buy_price": 100,
            "currency": "USD",
            "customs_rate": 0,
            "marketplaces": ["coupang", "smartstore"],
        })
        assert resp.status_code == 200
        results = resp.get_json()["results"]
        prices = {r["marketplace"]: r["recommended_price"] for r in results}
        # 쿠팡(10.8%) 수수료 > 스마트스토어(5%) → 쿠팡 권장가가 더 높아야 함
        assert prices["coupang"] > prices["smartstore"]

    def test_compare_zero_price_returns_400(self, client):
        """매입가 0 → 400."""
        resp = self._post(client, {"buy_price": 0, "currency": "USD"})
        assert resp.status_code == 400

    def test_compare_with_sell_price(self, client):
        """sell_price 직접 지정 → given_price 필드 반환."""
        resp = self._post(client, {
            "buy_price": 100,
            "currency": "USD",
            "customs_rate": 0,
            "sell_price": 200000,
            "marketplaces": ["coupang"],
        })
        assert resp.status_code == 200
        result = resp.get_json()["results"][0]
        assert result["given_price"] is not None


# ---------------------------------------------------------------------------
# 공개 API /api/v1/pricing/calculate
# ---------------------------------------------------------------------------

class TestApiPricingCalculate:
    def test_api_pricing_calculate_200(self, client):
        """POST /api/v1/pricing/calculate → 200."""
        resp = client.post(
            "/api/v1/pricing/calculate",
            json={
                "buy_price": 100,
                "currency": "USD",
                "marketplace": "coupang",
                "customs_rate": 20,
                "target_margin_pct": 22,
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "result" in data


# ---------------------------------------------------------------------------
# MarginCalculator 단위 테스트
# ---------------------------------------------------------------------------

class TestMarginCalculatorUnit:
    """MarginCalculator 직접 호출 단위 테스트."""

    def test_krw_buy_no_customs_coupang_22pct(self):
        """KRW 매입 + 면세 + 쿠팡 22% 목표 마진 → 권장가 > 원가."""
        from src.seller_console.margin_calculator import (
            CostInput, MarginCalculator, MarketInput,
        )
        cost = CostInput(
            buy_price=Decimal("50000"),
            buy_currency="KRW",
            customs_rate=Decimal("0"),
        )
        market = MarketInput(
            marketplace="coupang",
            commission_rate=Decimal("10.8"),
            target_margin_pct=Decimal("22"),
        )
        calc = MarginCalculator()
        result = calc.calculate(cost, market)
        assert result.recommended_price > result.total_landed_cost
        assert result.actual_margin_pct >= Decimal("18")  # ~22% ± rounding (10원 단위)

    def test_usd_buy_fx_override(self):
        """USD 매입 + 수동 환율 1370 → cost_in_krw = 100 * 1370."""
        from src.seller_console.margin_calculator import (
            CostInput, MarginCalculator, MarketInput,
        )
        cost = CostInput(
            buy_price=Decimal("100"),
            buy_currency="USD",
            customs_rate=Decimal("0"),
            fx_override=Decimal("1370"),
        )
        market = MarketInput(
            marketplace="coupang",
            commission_rate=Decimal("10.8"),
            target_margin_pct=Decimal("22"),
        )
        calc = MarginCalculator()
        result = calc.calculate(cost, market)
        assert result.cost_in_krw == Decimal("137000")

    def test_customs_over_threshold(self):
        """면세 임계 초과 → customs_in_krw > 0."""
        from src.seller_console.margin_calculator import (
            CostInput, MarginCalculator, MarketInput,
        )
        cost = CostInput(
            buy_price=Decimal("200000"),
            buy_currency="KRW",
            customs_rate=Decimal("0.20"),
            customs_threshold_krw=Decimal("150000"),
        )
        market = MarketInput(
            marketplace="coupang",
            commission_rate=Decimal("10.8"),
        )
        calc = MarginCalculator()
        result = calc.calculate(cost, market)
        assert result.customs_in_krw == Decimal("40000")  # 200000 * 0.20

    def test_customs_under_threshold(self):
        """면세 임계 미달 → customs_in_krw = 0."""
        from src.seller_console.margin_calculator import (
            CostInput, MarginCalculator, MarketInput,
        )
        cost = CostInput(
            buy_price=Decimal("100000"),
            buy_currency="KRW",
            customs_rate=Decimal("0.20"),
            customs_threshold_krw=Decimal("150000"),
        )
        market = MarketInput(
            marketplace="coupang",
            commission_rate=Decimal("10.8"),
        )
        calc = MarginCalculator()
        result = calc.calculate(cost, market)
        assert result.customs_in_krw == Decimal("0")

    def test_compare_four_marketplaces(self):
        """4개 마켓 비교 → 4개 결과."""
        from src.seller_console.margin_calculator import CostInput, MarginCalculator
        cost = CostInput(
            buy_price=Decimal("100"),
            buy_currency="USD",
            customs_rate=Decimal("0"),
            fx_override=Decimal("1370"),
        )
        calc = MarginCalculator()
        results = calc.compare_marketplaces(
            cost,
            marketplaces=["coupang", "smartstore", "11st", "kohganemultishop"],
        )
        assert len(results) == 4
        mp_ids = [r.marketplace for r in results]
        assert "coupang" in mp_ids
        assert "smartstore" in mp_ids

    def test_compare_commission_rates_from_percenty(self):
        """percenty MARKET_PRICE_POLICY 수수료율 정확히 매핑."""
        from src.seller_console.margin_calculator import (
            CostInput, MarginCalculator, default_commission_rate,
        )
        # 쿠팡 10.8%, 스마트스토어 5%, 11번가 12%
        assert default_commission_rate("coupang") == Decimal("10.8")
        assert default_commission_rate("smartstore") == Decimal("5.0")
        assert default_commission_rate("11st") == Decimal("12.0")
        # 자체몰 기본값 (3%)
        assert default_commission_rate("kohganemultishop") == Decimal("3")

    def test_reverse_target_price(self):
        """역산 판매가: 실제 마진율이 목표 마진에 근접해야 함."""
        from src.seller_console.margin_calculator import (
            CostInput, MarginCalculator, MarketInput,
        )
        cost = CostInput(
            buy_price=Decimal("100000"),
            buy_currency="KRW",
            customs_rate=Decimal("0"),
        )
        market = MarketInput(
            marketplace="coupang",
            commission_rate=Decimal("10.8"),
            target_margin_pct=Decimal("22"),
        )
        calc = MarginCalculator()
        price = calc.reverse_target_price(cost, market)
        assert price > Decimal("100000")
        # 실제 마진율 검증 (~22%)
        result = calc.calculate(cost, market)
        assert abs(float(result.actual_margin_pct) - 22.0) < 3.0

    def test_no_fx_module_graceful_fallback(self):
        """FX 모듈 미존재 시 기본 환율로 graceful fallback."""
        from src.seller_console.margin_calculator import (
            CostInput, MarginCalculator, MarketInput,
        )
        cost = CostInput(
            buy_price=Decimal("100"),
            buy_currency="USD",
            customs_rate=Decimal("0"),
            # fx_override 없이 → _load_fx_rates() 사용
        )
        market = MarketInput(
            marketplace="coupang",
            commission_rate=Decimal("10.8"),
        )
        calc = MarginCalculator()
        # 예외 없이 실행되어야 함
        result = calc.calculate(cost, market)
        assert result.cost_in_krw > Decimal("0")
        assert result.recommended_price > Decimal("0")
