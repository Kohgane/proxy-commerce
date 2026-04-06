"""tests/test_margin_calculator.py — 마진 계산기 단위 테스트."""

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# FeeStructure
# ──────────────────────────────────────────────────────────

class TestFeeStructure:
    """마켓별 수수료 구조 테스트."""

    def test_coupang_default_fee(self):
        """쿠팡 기본 수수료율 확인."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        rate = fs.get_sale_fee_rate('coupang', 'default')
        assert rate == 10.8

    def test_naver_default_fee(self):
        """네이버 기본 수수료율 확인."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        sale_rate = fs.get_sale_fee_rate('naver', 'default')
        assert sale_rate == 6.0

    def test_naver_total_fee_includes_pay_fee(self):
        """네이버 총 수수료 = 판매수수료 + 네이버페이수수료."""
        from src.margin.fee_structure import FeeStructure, NAVER_PAY_FEE
        fs = FeeStructure()
        total = fs.get_total_fee_rate('naver', 'default')
        sale = fs.get_sale_fee_rate('naver', 'default')
        assert total == pytest.approx(sale + NAVER_PAY_FEE, abs=0.01)

    def test_coupang_electronics_fee(self):
        """쿠팡 전자제품 수수료율."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        rate = fs.get_sale_fee_rate('coupang', 'electronics')
        assert rate == 10.8

    def test_coupang_food_fee_higher(self):
        """쿠팡 식품 수수료율은 전자보다 높음."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        food_rate = fs.get_sale_fee_rate('coupang', 'food')
        electronics_rate = fs.get_sale_fee_rate('coupang', 'electronics')
        assert food_rate > electronics_rate

    def test_naver_electronics_fee_low(self):
        """네이버 전자제품 수수료율은 낮음."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        rate = fs.get_sale_fee_rate('naver', 'electronics')
        assert rate == 2.0

    def test_unsupported_platform_raises(self):
        """지원하지 않는 플랫폼 오류."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        with pytest.raises(ValueError, match='지원하지 않는 플랫폼'):
            fs.get_total_fee_rate('shopify', 'default')

    def test_coupang_fee_breakdown(self):
        """쿠팡 수수료 항목 분리."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        breakdown = fs.get_fee_breakdown('coupang', 100000, 'default')
        assert breakdown['sale_fee_rate'] == 10.8
        assert breakdown['payment_fee_rate'] == 0.0
        assert breakdown['sale_fee'] == pytest.approx(10800, abs=1)
        assert breakdown['total_fee'] == pytest.approx(10800, abs=1)

    def test_naver_fee_breakdown(self):
        """네이버 수수료 항목 분리."""
        from src.margin.fee_structure import FeeStructure, NAVER_PAY_FEE
        fs = FeeStructure()
        breakdown = fs.get_fee_breakdown('naver', 100000, 'default')
        assert breakdown['payment_fee_rate'] == NAVER_PAY_FEE
        assert breakdown['payment_fee'] == pytest.approx(3740, abs=1)
        assert breakdown['total_fee'] == pytest.approx(9740, abs=1)

    def test_coupang_rocket_delivery_adds_fee(self):
        """쿠팡 로켓배송 추가 수수료."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        normal = fs.get_total_fee_rate('coupang', 'default')
        rocket = fs.get_total_fee_rate('coupang', 'default', {'rocket_delivery': True})
        assert rocket > normal

    def test_list_categories_coupang(self):
        """쿠팡 카테고리 목록 반환."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        categories = fs.list_categories('coupang')
        assert 'default' in categories
        assert 'electronics' in categories
        assert 'food' in categories

    def test_list_categories_naver(self):
        """네이버 카테고리 목록 반환."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        categories = fs.list_categories('naver')
        assert 'default' in categories
        assert 'electronics' in categories

    def test_category_case_insensitive(self):
        """카테고리 대소문자 무관."""
        from src.margin.fee_structure import FeeStructure
        fs = FeeStructure()
        rate1 = fs.get_sale_fee_rate('coupang', 'Electronics')
        rate2 = fs.get_sale_fee_rate('coupang', 'electronics')
        assert rate1 == rate2


# ──────────────────────────────────────────────────────────
# ShippingCost
# ──────────────────────────────────────────────────────────

class TestShippingCost:
    """배송비 계산 테스트."""

    def test_intl_shipping_us_basic(self):
        """미국 → 한국 국제배송비."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        cost = sc.calculate_international_shipping(1.0, 'us')
        assert cost > 0

    def test_intl_shipping_jp_cheaper_than_us(self):
        """일본 배송비는 미국보다 저렴."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        us_cost = sc.calculate_international_shipping(1.0, 'us')
        jp_cost = sc.calculate_international_shipping(1.0, 'jp')
        assert jp_cost < us_cost

    def test_intl_shipping_by_marketplace(self):
        """마켓플레이스로 배송비 계산."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        cost = sc.calculate_international_shipping(1.0, marketplace='amazon_us')
        assert cost > 0

    def test_intl_shipping_weight_proportional(self):
        """무거울수록 배송비 증가."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        cost1 = sc.calculate_international_shipping(1.0, 'us')
        cost2 = sc.calculate_international_shipping(2.0, 'us')
        assert cost2 > cost1

    def test_customs_fee_duty_free(self):
        """150달러 이하 면세."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        result = sc.calculate_customs_fee(100.0)
        assert result['is_duty_free'] is True
        assert result['import_duty'] == 0.0
        assert result['vat'] == 0.0

    def test_customs_fee_dutiable(self):
        """150달러 초과 시 관세 부과."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        result = sc.calculate_customs_fee(200.0)
        assert result['is_duty_free'] is False
        assert result['import_duty'] > 0
        assert result['vat'] > 0
        assert result['total'] > result['customs_fee']

    def test_customs_fee_boundary_150(self):
        """150달러 정확히 면세."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        result = sc.calculate_customs_fee(150.0)
        assert result['is_duty_free'] is True

    def test_customs_fee_boundary_151(self):
        """151달러 과세."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        result = sc.calculate_customs_fee(151.0)
        assert result['is_duty_free'] is False

    def test_domestic_shipping_standard(self):
        """기본 국내배송비."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost()
        cost = sc.calculate_domestic_shipping(30000)
        assert cost == 3000.0

    def test_domestic_shipping_free_high_price(self):
        """고가 상품 무료 국내배송."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost()
        cost = sc.calculate_domestic_shipping(60000)
        assert cost == 0.0

    def test_domestic_shipping_free_flag(self):
        """무료배송 플래그 사용."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost()
        cost = sc.calculate_domestic_shipping(10000, free_shipping=True)
        assert cost == 0.0

    def test_total_shipping_calculation(self):
        """총 배송비 계산."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        result = sc.calculate_total_shipping(
            weight_kg=0.5,
            product_price_usd=50.0,
            origin_country='us',
            sale_price_krw=30000,
        )
        assert result['total'] > 0
        assert result['international_shipping'] > 0
        assert 'customs' in result
        assert result['domestic_shipping'] == 3000.0

    def test_set_exchange_rate(self):
        """환율 업데이트."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        cost1 = sc.calculate_international_shipping(1.0, 'us')
        sc.set_exchange_rate(1400.0)
        cost2 = sc.calculate_international_shipping(1.0, 'us')
        assert cost2 > cost1

    def test_exchange_rate_property(self):
        """환율 프로퍼티."""
        from src.margin.shipping_cost import ShippingCost
        sc = ShippingCost(krw_per_usd=1350.0)
        assert sc.exchange_rate == 1350.0


# ──────────────────────────────────────────────────────────
# MarginCalculator
# ──────────────────────────────────────────────────────────

class TestMarginCalculator:
    """마진 계산기 테스트."""

    def test_basic_calculation_usd_coupang(self):
        """기본 마진 계산 (USD → 쿠팡)."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.calculate(
            foreign_price=29.99,
            sale_price_krw=65000,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
        )
        assert result['cost_krw'] == pytest.approx(29.99 * 1350.0, abs=1)
        assert result['sale_price_krw'] == 65000
        assert 'margin_rate' in result
        assert 'is_profitable' in result

    def test_basic_calculation_jpy_naver(self):
        """JPY → 네이버 마진 계산."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator()
        result = calc.calculate(
            foreign_price=2980,
            sale_price_krw=35000,
            currency='JPY',
            marketplace='amazon_jp',
            platform='naver',
        )
        assert result['currency'] == 'JPY'
        assert result['cost_krw'] > 0
        assert 'fee_rate' in result

    def test_basic_calculation_cny_coupang(self):
        """CNY → 쿠팡 마진 계산."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator()
        result = calc.calculate(
            foreign_price=79.9,
            sale_price_krw=25000,
            currency='CNY',
            marketplace='taobao',
            platform='coupang',
        )
        assert result['cost_krw'] > 0

    def test_profitable_high_sale_price(self):
        """충분히 높은 판매가 → 수익."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.calculate(
            foreign_price=10.0,   # 10 USD = 13,500 KRW 원가
            sale_price_krw=100000,  # 10만원 판매
            currency='USD',
        )
        assert result['is_profitable'] is True
        assert result['margin_rate'] > 0

    def test_unprofitable_low_sale_price(self):
        """너무 낮은 판매가 → 손실."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.calculate(
            foreign_price=30.0,   # 30 USD = 40,500 KRW 원가
            sale_price_krw=10000,  # 1만원 판매 (원가 이하)
            currency='USD',
        )
        assert result['is_profitable'] is False
        assert result['net_revenue'] < 0

    def test_margin_rate_formula(self):
        """마진율 공식 검증."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.calculate(
            foreign_price=10.0,
            sale_price_krw=100000,
            currency='USD',
            platform='coupang',
            category='default',
        )
        # 마진율 = 순수익 / 판매가 × 100
        expected_margin_rate = result['net_revenue'] / result['sale_price_krw'] * 100
        assert result['margin_rate'] == pytest.approx(expected_margin_rate, abs=0.01)

    def test_fee_amount_formula(self):
        """수수료 금액 검증."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator()
        result = calc.calculate(
            foreign_price=10.0,
            sale_price_krw=50000,
            currency='USD',
            platform='coupang',
            category='default',
        )
        expected_fee = 50000 * result['fee_rate'] / 100
        assert result['fee_amount'] == pytest.approx(expected_fee, abs=1)

    def test_total_cost_formula(self):
        """총비용 = 원가 + 배송비."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.calculate(
            foreign_price=10.0,
            sale_price_krw=50000,
            currency='USD',
        )
        expected_total = (
            result['cost_krw']
            + result['international_shipping']
            + result['customs_total']
            + result['domestic_shipping']
        )
        assert result['total_cost'] == pytest.approx(expected_total, abs=1)

    def test_krw_price_no_conversion(self):
        """KRW 상품 환율 변환 없음."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator()
        result = calc.calculate(
            foreign_price=50000,
            sale_price_krw=80000,
            currency='KRW',
            marketplace='coupang',
        )
        assert result['exchange_rate'] == 1.0
        assert result['cost_krw'] == pytest.approx(50000, abs=1)

    def test_with_fx_service(self):
        """실시간 환율 서비스 연동."""
        mock_fx = MagicMock()
        mock_fx.get_rate.return_value = Decimal('1400')
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(fx_service=mock_fx)
        result = calc.calculate(
            foreign_price=10.0,
            sale_price_krw=50000,
            currency='USD',
        )
        assert result['exchange_rate'] == pytest.approx(1400.0, abs=0.1)
        assert result['cost_krw'] == pytest.approx(14000, abs=1)

    def test_fx_service_fallback_on_error(self):
        """환율 서비스 오류 시 기본값 사용."""
        mock_fx = MagicMock()
        mock_fx.get_rate.side_effect = Exception("FX 서비스 오류")
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(fx_service=mock_fx, krw_per_usd=1350.0)
        result = calc.calculate(
            foreign_price=10.0,
            sale_price_krw=50000,
            currency='USD',
        )
        # fallback 기본값 1350 또는 DEFAULT_RATES_TO_KRW['USD']
        assert result['cost_krw'] > 0


# ──────────────────────────────────────────────────────────
# MarginCalculator 역계산
# ──────────────────────────────────────────────────────────

class TestMarginCalculatorReverse:
    """마진 계산기 역계산 테스트."""

    def test_reverse_calculate_basic(self):
        """역계산 기본 동작."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.reverse_calculate(
            foreign_price=20.0,
            target_margin_rate=20.0,
            currency='USD',
            platform='coupang',
        )
        assert result['target_margin_rate'] == 20.0
        assert result['optimal_sale_price'] > 0
        assert result['rounded_sale_price'] > 0
        # 반올림 판매가는 100원 단위
        assert result['rounded_sale_price'] % 100 == 0

    def test_reverse_calculate_actual_margin_close_to_target(self):
        """역계산 실제 마진율이 목표에 근접."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.reverse_calculate(
            foreign_price=10.0,
            target_margin_rate=20.0,
            currency='USD',
            platform='coupang',
        )
        # 실제 마진율이 목표(20%)보다 크거나 같아야 함 (100원 올림)
        assert result['actual_margin_rate'] >= 19.0  # 반올림 오차 허용

    def test_reverse_calculate_zero_margin(self):
        """0% 마진율 역계산 (BEP 계산)."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.reverse_calculate(
            foreign_price=10.0,
            target_margin_rate=0.0,
            currency='USD',
            platform='coupang',
        )
        assert result['optimal_sale_price'] > 0
        # BEP: 마진율 ≈ 0
        assert result['actual_margin_rate'] >= 0

    def test_reverse_calculate_impossible_margin_raises(self):
        """불가능한 마진율 (수수료+마진 > 100%)."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator()
        with pytest.raises(ValueError, match='초과'):
            calc.reverse_calculate(
                foreign_price=10.0,
                target_margin_rate=95.0,  # 수수료 ~10% + 마진 95% > 100%
                currency='USD',
                platform='coupang',
            )

    def test_reverse_calculate_contains_required_fields(self):
        """역계산 결과 필드 확인."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.reverse_calculate(
            foreign_price=15.0,
            target_margin_rate=15.0,
            currency='USD',
        )
        required_keys = [
            'target_margin_rate', 'optimal_sale_price', 'rounded_sale_price',
            'cost_krw', 'total_cost', 'fee_rate', 'actual_margin_rate',
        ]
        for key in required_keys:
            assert key in result

    def test_reverse_calculate_rounded_price_greater_than_optimal(self):
        """반올림 판매가 ≥ 최적 판매가."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.reverse_calculate(
            foreign_price=10.0,
            target_margin_rate=15.0,
            currency='USD',
        )
        assert result['rounded_sale_price'] >= result['optimal_sale_price']


# ──────────────────────────────────────────────────────────
# MarginCalculator 일괄 계산
# ──────────────────────────────────────────────────────────

class TestMarginCalculatorBulk:
    """마진 계산기 일괄 계산 테스트."""

    def _make_product(self, price=20.0, sale=55000, currency='USD'):
        return {
            'foreign_price': price,
            'sale_price_krw': sale,
            'currency': currency,
        }

    def test_bulk_calculate_success(self):
        """일괄 계산 성공."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        products = [self._make_product(price=i * 5 + 5, sale=i * 10000 + 20000) for i in range(5)]
        results = calc.bulk_calculate(products)
        assert len(results) == 5
        assert all(r['success'] for r in results)

    def test_bulk_calculate_with_error(self):
        """일부 상품 계산 실패 (지원하지 않는 플랫폼)."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        products = [
            self._make_product(),
            {'foreign_price': 10.0, 'sale_price_krw': 5000, 'currency': 'USD', 'platform': 'shopify'},
        ]
        results = calc.bulk_calculate(products)
        assert results[0]['success'] is True
        assert results[1]['success'] is False
        assert 'error' in results[1]

    def test_bulk_calculate_product_index(self):
        """결과에 product_index 포함."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        products = [self._make_product() for _ in range(3)]
        results = calc.bulk_calculate(products)
        for i, result in enumerate(results):
            assert result['product_index'] == i

    def test_generate_report_summary(self):
        """리포트 요약 통계."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        products = [
            self._make_product(price=5, sale=100000),   # 수익
            self._make_product(price=5, sale=100000),   # 수익
            self._make_product(price=100, sale=5000),   # 손실
        ]
        report = calc.generate_report(products)
        assert report['total_products'] == 3
        assert report['successful_count'] == 3
        assert report['profitable_count'] == 2
        assert report['avg_margin_rate'] is not None

    def test_generate_report_empty(self):
        """빈 상품 목록 리포트."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator()
        report = calc.generate_report([])
        assert report['total_products'] == 0
        assert report['profitable_count'] == 0
        assert report['avg_margin_rate'] == 0.0

    def test_generate_report_contains_results(self):
        """리포트에 results 포함."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        products = [self._make_product()]
        report = calc.generate_report(products)
        assert 'results' in report
        assert len(report['results']) == 1

    def test_generate_report_max_min_margin(self):
        """최대/최소 마진율."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        products = [
            self._make_product(price=5, sale=200000),   # 높은 마진
            self._make_product(price=5, sale=50000),    # 낮은 마진
        ]
        report = calc.generate_report(products)
        assert report['max_margin_rate'] >= report['min_margin_rate']


# ──────────────────────────────────────────────────────────
# Margin 패키지 수출 검증
# ──────────────────────────────────────────────────────────

class TestMarginPackageExports:
    """margin 패키지 수출 검증."""

    def test_margin_calculator_importable(self):
        """MarginCalculator 임포트 가능."""
        from src.margin import MarginCalculator
        assert MarginCalculator is not None

    def test_fee_structure_importable(self):
        """FeeStructure 임포트 가능."""
        from src.margin import FeeStructure
        assert FeeStructure is not None

    def test_shipping_cost_importable(self):
        """ShippingCost 임포트 가능."""
        from src.margin import ShippingCost
        assert ShippingCost is not None


# ──────────────────────────────────────────────────────────
# 통합: 마진 계산 + 환율 서비스
# ──────────────────────────────────────────────────────────

class TestMarginFXIntegration:
    """마진 계산기 + 환율 서비스 통합 테스트."""

    def test_margin_with_realtime_fx(self):
        """실시간 환율 서비스와 통합 계산."""
        from src.fx.rate_cache import RateCache
        from src.fx.realtime_rates import RealtimeRates
        from src.margin.calculator import MarginCalculator

        # 고정 환율로 캐시 설정
        cache = RateCache(ttl_seconds=3600)
        cache.set('USD', 'KRW', Decimal('1400'))
        fx = RealtimeRates(cache=cache)

        calc = MarginCalculator(fx_service=fx)
        result = calc.calculate(
            foreign_price=20.0,
            sale_price_krw=80000,
            currency='USD',
            platform='coupang',
        )
        assert result['exchange_rate'] == pytest.approx(1400.0, abs=0.1)
        assert result['cost_krw'] == pytest.approx(28000, abs=1)

    def test_margin_jpy_with_fx(self):
        """JPY 환율로 마진 계산."""
        from src.fx.rate_cache import RateCache
        from src.fx.realtime_rates import RealtimeRates
        from src.margin.calculator import MarginCalculator

        cache = RateCache(ttl_seconds=3600)
        cache.set('JPY', 'KRW', Decimal('9.5'))
        fx = RealtimeRates(cache=cache)

        calc = MarginCalculator(fx_service=fx)
        result = calc.calculate(
            foreign_price=2980,
            sale_price_krw=40000,
            currency='JPY',
            marketplace='amazon_jp',
            platform='naver',
        )
        assert result['exchange_rate'] == pytest.approx(9.5, abs=0.01)
        assert result['cost_krw'] == pytest.approx(2980 * 9.5, abs=1)

    def test_bulk_calculate_mixed_currencies(self):
        """혼합 통화 일괄 계산."""
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=1350.0)
        products = [
            {'foreign_price': 29.99, 'sale_price_krw': 65000, 'currency': 'USD'},
            {'foreign_price': 2980, 'sale_price_krw': 38000, 'currency': 'JPY'},
            {'foreign_price': 89.9, 'sale_price_krw': 22000, 'currency': 'CNY'},
        ]
        results = calc.bulk_calculate(products)
        assert len(results) == 3
        for result in results:
            assert result['success'] is True
            assert result['cost_krw'] > 0


# ==============================================================================
# Phase 110: RealTimeMarginCalculator (src/margin_calculator/) 테스트
# ==============================================================================

# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

def _ph110_sample_product(
    selling_price=30000, source_cost=10.0, currency='USD', exchange_rate=1300.0,
    international_shipping=3000.0, customs_duty_rate=8.0, domestic_shipping=2500.0,
    payment_fee_rate=2.0, packaging_cost=1000.0, labeling_cost=500.0,
    return_reserve_rate=2.0, misc_costs=0.0, category='electronics',
):
    return dict(
        selling_price=selling_price, source_cost=source_cost, currency=currency,
        exchange_rate=exchange_rate, international_shipping=international_shipping,
        customs_duty_rate=customs_duty_rate, domestic_shipping=domestic_shipping,
        payment_fee_rate=payment_fee_rate, packaging_cost=packaging_cost,
        labeling_cost=labeling_cost, return_reserve_rate=return_reserve_rate,
        misc_costs=misc_costs, category=category,
    )


# ─── Phase110: MarginConfig ───────────────────────────────────────────────────

class TestPh110MarginConfig:
    def _make(self):
        from src.margin_calculator.margin_config import MarginConfig
        return MarginConfig()

    def test_default_config_values(self):
        cfg = self._make()
        c = cfg.get_config()
        assert c['default_target_margin'] == 15.0
        assert c['critical_margin_threshold'] == 0.0
        assert c['warning_margin_threshold'] == 5.0
        assert c['exchange_spread_rate'] == 1.5
        assert c['vat_rate'] == 10.0

    def test_update_config(self):
        cfg = self._make()
        updated = cfg.update_config({'default_target_margin': 20.0})
        assert updated['default_target_margin'] == 20.0

    def test_update_unknown_key_ignored(self):
        cfg = self._make()
        cfg.update_config({'unknown_key': 999})
        assert 'unknown_key' not in cfg.get_config()

    def test_category_override(self):
        cfg = self._make()
        cfg.set_category_config('fashion', {'default_target_margin': 25.0})
        c = cfg.get_config(category='fashion')
        assert c['default_target_margin'] == 25.0

    def test_product_override(self):
        cfg = self._make()
        cfg.set_product_config('p1', {'vat_rate': 0.0})
        c = cfg.get_config(product_id='p1')
        assert c['vat_rate'] == 0.0

    def test_product_overrides_category(self):
        cfg = self._make()
        cfg.set_category_config('electronics', {'default_target_margin': 20.0})
        cfg.set_product_config('p1', {'default_target_margin': 30.0})
        c = cfg.get_config(product_id='p1', category='electronics')
        assert c['default_target_margin'] == 30.0

    def test_reset_to_defaults(self):
        cfg = self._make()
        cfg.update_config({'default_target_margin': 99.0})
        defaults = cfg.reset_to_defaults()
        assert defaults['default_target_margin'] == 15.0


# ─── Phase110: PlatformFeeCalculator ─────────────────────────────────────────

class TestPh110PlatformFeeCalculator:
    def _make(self):
        from src.margin_calculator.platform_fees import PlatformFeeCalculator
        return PlatformFeeCalculator()

    def test_coupang_electronics_fee(self):
        calc = self._make()
        fee = calc.get_platform_fee('coupang', 10000, category='electronics')
        assert fee == pytest.approx(800.0)

    def test_coupang_fashion_fee(self):
        calc = self._make()
        fee = calc.get_platform_fee('coupang', 10000, category='fashion')
        assert fee == pytest.approx(1080.0)

    def test_coupang_rocket_extra(self):
        calc = self._make()
        fee = calc.get_platform_fee('coupang', 10000, category='electronics', rocket_delivery=True)
        assert fee == pytest.approx(1000.0)

    def test_naver_fee(self):
        calc = self._make()
        fee = calc.get_platform_fee('naver', 10000)
        assert fee == pytest.approx(774.0)

    def test_internal_toss_fee(self):
        calc = self._make()
        fee = calc.get_platform_fee('internal', 10000, pg_method='toss')
        assert fee == pytest.approx(320.0)

    def test_unknown_channel_zero(self):
        calc = self._make()
        assert calc.get_platform_fee('unknown', 10000) == 0.0

    def test_get_fee_structure_coupang(self):
        calc = self._make()
        s = calc.get_fee_structure('coupang')
        assert s['channel'] == 'coupang'
        assert 'categories' in s

    def test_get_all_fee_structures(self):
        calc = self._make()
        all_fees = calc.get_all_fee_structures()
        assert set(all_fees.keys()) == {'coupang', 'naver', 'internal'}


# ─── Phase110: RealTimeMarginCalculator ──────────────────────────────────────

class TestPh110RealTimeMarginCalculator:
    def _make(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        return RealTimeMarginCalculator()

    def _reg(self, calc, pid='p1', **kwargs):
        data = _ph110_sample_product(**kwargs)
        calc.register_product(pid, data)
        return data

    def test_basic_margin_calculation(self):
        calc = self._make()
        self._reg(calc, 'p1', selling_price=30000, source_cost=10.0, exchange_rate=1300.0)
        result = calc.calculate_margin('p1')
        assert result.source_cost_krw == pytest.approx(13000.0)
        assert result.product_id == 'p1'

    def test_all_cost_items_nonnegative(self):
        calc = self._make()
        self._reg(calc, 'p1')
        r = calc.calculate_margin('p1')
        for f in ('source_cost_krw', 'international_shipping', 'customs_duty',
                  'vat', 'domestic_shipping', 'platform_fee', 'payment_fee',
                  'exchange_loss', 'packaging_cost', 'labeling_cost',
                  'return_reserve', 'misc_costs'):
            assert getattr(r, f) >= 0

    def test_net_profit_formula(self):
        calc = self._make()
        self._reg(calc, 'p1')
        r = calc.calculate_margin('p1')
        assert r.net_profit == pytest.approx(r.selling_price - r.total_cost, abs=0.01)

    def test_margin_rate_formula(self):
        calc = self._make()
        self._reg(calc, 'p1', selling_price=30000)
        r = calc.calculate_margin('p1')
        expected = r.net_profit / r.selling_price * 100
        assert r.margin_rate == pytest.approx(expected, abs=0.01)

    def test_customs_duty_calculation(self):
        calc = self._make()
        self._reg(calc, 'p1', source_cost=10.0, exchange_rate=1300.0,
                  international_shipping=3000.0, customs_duty_rate=8.0)
        r = calc.calculate_margin('p1')
        assert r.customs_duty == pytest.approx(1280.0)

    def test_vat_calculation(self):
        calc = self._make()
        self._reg(calc, 'p1', source_cost=10.0, exchange_rate=1300.0,
                  international_shipping=3000.0, customs_duty_rate=8.0)
        r = calc.calculate_margin('p1')
        assert r.vat == pytest.approx(1728.0)

    def test_exchange_loss(self):
        calc = self._make()
        self._reg(calc, 'p1', source_cost=10.0, exchange_rate=1300.0)
        r = calc.calculate_margin('p1')
        assert r.exchange_loss == pytest.approx(195.0)

    def test_coupang_channel(self):
        calc = self._make()
        self._reg(calc, 'p1', selling_price=30000, category='electronics')
        r = calc.calculate_margin('p1', 'coupang')
        assert r.channel == 'coupang'
        assert r.platform_fee == pytest.approx(2400.0)

    def test_naver_channel(self):
        calc = self._make()
        self._reg(calc, 'p1', selling_price=30000)
        r = calc.calculate_margin('p1', 'naver')
        assert r.channel == 'naver'

    def test_usd_product(self):
        calc = self._make()
        self._reg(calc, 'p1', source_cost=15.0, currency='USD', exchange_rate=1350.0)
        r = calc.calculate_margin('p1')
        assert r.source_cost_krw == pytest.approx(20250.0)

    def test_jpy_product(self):
        calc = self._make()
        self._reg(calc, 'p1', source_cost=1500.0, currency='JPY', exchange_rate=9.0)
        r = calc.calculate_margin('p1')
        assert r.source_cost_krw == pytest.approx(13500.0)

    def test_cny_product(self):
        calc = self._make()
        self._reg(calc, 'p1', source_cost=50.0, currency='CNY', exchange_rate=185.0)
        r = calc.calculate_margin('p1')
        assert r.source_cost_krw == pytest.approx(9250.0)

    def test_loss_product(self):
        calc = self._make()
        calc.register_product('p_loss', {'selling_price': 5000, 'source_cost': 10.0,
                                          'exchange_rate': 1300.0, 'international_shipping': 5000.0})
        r = calc.calculate_margin('p_loss')
        assert r.net_profit < 0

    def test_cache_hit(self):
        calc = self._make()
        self._reg(calc, 'p1')
        r1 = calc.calculate_margin('p1', use_cache=True)
        r2 = calc.calculate_margin('p1', use_cache=True)
        assert r1.result_id == r2.result_id

    def test_cache_invalidation_on_update(self):
        calc = self._make()
        self._reg(calc, 'p1', selling_price=30000)
        r1 = calc.calculate_margin('p1', use_cache=True)
        calc.update_product('p1', {'selling_price': 50000})
        r2 = calc.calculate_margin('p1', use_cache=True)
        assert r1.result_id != r2.result_id
        assert r2.selling_price == 50000

    def test_bulk_margins(self):
        calc = self._make()
        for i in range(5):
            self._reg(calc, f'p{i}', selling_price=30000 + i * 1000)
        results = calc.calculate_bulk_margins()
        assert len(results) == 5

    def test_recalculate_all(self):
        calc = self._make()
        self._reg(calc, 'p1')
        self._reg(calc, 'p2')
        result = calc.recalculate_all()
        assert result['total'] > 0

    def test_history_saved(self):
        calc = self._make()
        self._reg(calc, 'p1')
        calc.calculate_margin('p1', use_cache=False)
        calc.calculate_margin('p1', use_cache=False)
        history = calc.get_history(product_id='p1')
        assert len(history) >= 2

    def test_to_dict_has_required_fields(self):
        calc = self._make()
        self._reg(calc, 'p1')
        d = calc.calculate_margin('p1').to_dict()
        for field in ('product_id', 'margin_rate', 'net_profit', 'calculated_at'):
            assert field in d


# ─── Phase110: CostBreakdownService ──────────────────────────────────────────

class TestPh110CostBreakdown:
    def _make(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.cost_breakdown import CostBreakdownService
        calc = RealTimeMarginCalculator()
        calc.register_product('p1', _ph110_sample_product(selling_price=30000))
        return CostBreakdownService(calc)

    def test_breakdown_structure(self):
        svc = self._make()
        bd = svc.get_cost_breakdown('p1')
        assert all(k in bd for k in ('costs', 'percentages', 'total_cost', 'net_profit', 'margin_rate'))

    def test_all_cost_keys_present(self):
        svc = self._make()
        bd = svc.get_cost_breakdown('p1')
        for key in ('source_cost_krw', 'international_shipping', 'customs_duty', 'vat',
                    'domestic_shipping', 'platform_fee', 'payment_fee', 'exchange_spread',
                    'packaging_cost', 'labeling_cost', 'return_reserve', 'misc_costs'):
            assert key in bd['costs']

    def test_percentages_plus_profit_approx_100(self):
        svc = self._make()
        bd = svc.get_cost_breakdown('p1')
        sp = bd['selling_price']
        if sp > 0:
            total_pct = sum(bd['percentages'].values())
            profit_pct = bd['net_profit'] / sp * 100
            assert total_pct + profit_pct == pytest.approx(100.0, abs=0.2)


# ─── Phase110: MarginAlertService ────────────────────────────────────────────

class TestPh110MarginAlerts:
    def _calc_with(self, pid, selling, cost_krw):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        calc = RealTimeMarginCalculator()
        calc.register_product(pid, {'selling_price': selling, 'source_cost': cost_krw,
                                     'currency': 'KRW', 'exchange_rate': 1.0})
        return calc

    def test_critical_alert_loss(self):
        from src.margin_calculator.margin_alerts import MarginAlertService, AlertSeverity
        calc = self._calc_with('p_loss', 5000, 10000)
        svc = MarginAlertService(calculator=calc)
        alerts = svc.check_margin_alerts('p_loss')
        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_good_product_no_alert(self):
        from src.margin_calculator.margin_alerts import MarginAlertService
        calc = self._calc_with('p_good', 30000, 1000)
        svc = MarginAlertService(calculator=calc)
        alerts = svc.check_margin_alerts('p_good')
        assert len(alerts) == 0

    def test_acknowledge_alert(self):
        from src.margin_calculator.margin_alerts import MarginAlertService
        calc = self._calc_with('p_loss', 5000, 10000)
        svc = MarginAlertService(calculator=calc)
        alerts = svc.check_margin_alerts('p_loss')
        acked = svc.acknowledge_alert(alerts[0].alert_id)
        assert acked.acknowledged is True

    def test_acknowledge_nonexistent_returns_none(self):
        from src.margin_calculator.margin_alerts import MarginAlertService
        svc = MarginAlertService()
        assert svc.acknowledge_alert('nonexistent') is None

    def test_dedup_prevents_duplicate_alerts(self):
        from src.margin_calculator.margin_alerts import MarginAlertService
        calc = self._calc_with('p_loss', 5000, 10000)
        svc = MarginAlertService(calculator=calc)
        a1 = svc.check_margin_alerts('p_loss')
        a2 = svc.check_margin_alerts('p_loss')
        assert len(a1) == 1
        assert len(a2) == 0

    def test_alert_summary_structure(self):
        from src.margin_calculator.margin_alerts import MarginAlertService, AlertSeverity
        svc = MarginAlertService()
        summary = svc.get_alert_summary()
        assert AlertSeverity.CRITICAL.value in summary

    def test_custom_threshold(self):
        from src.margin_calculator.margin_alerts import MarginAlertService
        svc = MarginAlertService()
        svc.set_threshold('p1', critical=-10.0, warning=2.0, target=20.0)
        assert svc._custom_thresholds['p1']['critical'] == -10.0

    def test_alert_to_dict(self):
        from src.margin_calculator.margin_alerts import MarginAlertService
        calc = self._calc_with('p_loss', 5000, 10000)
        svc = MarginAlertService(calculator=calc)
        alerts = svc.check_margin_alerts('p_loss')
        d = alerts[0].to_dict()
        assert 'alert_id' in d and 'severity' in d and 'suggestion' in d


# ─── Phase110: MarginSimulator ───────────────────────────────────────────────

class TestPh110MarginSimulator:
    def _make(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.margin_simulator import MarginSimulator
        calc = RealTimeMarginCalculator()
        calc.register_product('p1', _ph110_sample_product(selling_price=30000))
        return MarginSimulator(calc)

    def test_price_increase_improves_margin(self):
        sim = self._make()
        r = sim.simulate_price_change('p1', 40000)
        assert r['delta_margin_rate'] > 0

    def test_price_decrease_lowers_margin(self):
        sim = self._make()
        r = sim.simulate_price_change('p1', 20000)
        assert r['delta_margin_rate'] < 0

    def test_exchange_rate_increase_lowers_margin(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.margin_simulator import MarginSimulator
        calc = RealTimeMarginCalculator()
        calc.register_product('p1', _ph110_sample_product(exchange_rate=1300.0))
        sim = MarginSimulator(calc)
        r = sim.simulate_exchange_rate('p1', 1500.0)
        assert r['delta_margin_rate'] < 0

    def test_cost_change_lowers_profit(self):
        sim = self._make()
        r = sim.simulate_cost_change('p1', 'domestic_shipping', 5000.0)
        assert r['delta_net_profit'] < 0

    def test_break_even_approx_zero_margin(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.margin_simulator import MarginSimulator
        calc = RealTimeMarginCalculator()
        calc.register_product('p1', _ph110_sample_product())
        sim = MarginSimulator(calc)
        r = sim.find_break_even_price('p1')
        assert abs(r['margin_rate_at_break_even']) < 1.0

    def test_target_margin_price(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.margin_simulator import MarginSimulator
        calc = RealTimeMarginCalculator()
        calc.register_product('p1', _ph110_sample_product())
        sim = MarginSimulator(calc)
        r = sim.find_target_margin_price('p1', 15.0)
        assert abs(r['margin_rate_achieved'] - 15.0) < 1.0

    def test_what_if_analysis(self):
        sim = self._make()
        scenarios = [
            {'name': 'S1', 'changes': {'selling_price': 35000}},
            {'name': 'S2', 'changes': {'selling_price': 25000}},
        ]
        r = sim.what_if_analysis('p1', scenarios)
        assert len(r['scenarios']) == 2
        assert 'baseline' in r


# ─── Phase110: ProfitabilityAnalyzer ─────────────────────────────────────────

class TestPh110Profitability:
    def _make(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.profitability import ProfitabilityAnalyzer
        calc = RealTimeMarginCalculator()
        for i in range(5):
            calc.register_product(f'p{i}', {
                'selling_price': 30000, 'source_cost': 3000.0 + i * 2000,
                'currency': 'KRW', 'exchange_rate': 1.0,
            })
        return ProfitabilityAnalyzer(calc)

    def test_ranking_top_descending(self):
        ana = self._make()
        ranking = ana.get_profitability_ranking(limit=3, reverse=True)
        for i in range(len(ranking) - 1):
            assert ranking[i]['margin_rate'] >= ranking[i + 1]['margin_rate']

    def test_ranking_bottom_ascending(self):
        ana = self._make()
        ranking = ana.get_profitability_ranking(limit=3, reverse=False)
        for i in range(len(ranking) - 1):
            assert ranking[i]['margin_rate'] <= ranking[i + 1]['margin_rate']

    def test_loss_products_correctly_identified(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.profitability import ProfitabilityAnalyzer
        calc = RealTimeMarginCalculator()
        calc.register_product('p_loss', {'selling_price': 5000, 'source_cost': 10000,
                                          'currency': 'KRW', 'exchange_rate': 1.0})
        calc.register_product('p_good', {'selling_price': 30000, 'source_cost': 5000,
                                          'currency': 'KRW', 'exchange_rate': 1.0})
        ana = ProfitabilityAnalyzer(calc)
        loss = ana.get_loss_products()
        pids = [p['product_id'] for p in loss]
        assert 'p_loss' in pids
        assert 'p_good' not in pids

    def test_low_margin_products(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.profitability import ProfitabilityAnalyzer
        calc = RealTimeMarginCalculator()
        calc.register_product('p_low', {'selling_price': 10000, 'source_cost': 9700,
                                         'currency': 'KRW', 'exchange_rate': 1.0})
        ana = ProfitabilityAnalyzer(calc)
        low = ana.get_low_margin_products(threshold=10.0)
        assert any(p['product_id'] == 'p_low' for p in low)

    def test_distribution_structure(self):
        ana = self._make()
        dist = ana.get_profitability_distribution()
        assert 'distribution' in dist
        assert 'total_products' in dist

    def test_channel_profitability_all_channels(self):
        ana = self._make()
        cp = ana.get_channel_profitability()
        assert set(cp.keys()) == {'coupang', 'naver', 'internal'}


# ─── Phase110: MarginTrendAnalyzer ───────────────────────────────────────────

class TestPh110MarginTrend:
    def _make(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.margin_trend import MarginTrendAnalyzer
        calc = RealTimeMarginCalculator()
        calc.register_product('p1', _ph110_sample_product())
        return MarginTrendAnalyzer(calc)

    def test_record_returns_point(self):
        ana = self._make()
        pt = ana.record('p1')
        assert pt.product_id == 'p1'

    def test_product_trend(self):
        ana = self._make()
        ana.record('p1')
        ana.record('p1')
        trend = ana.get_product_trend('p1')
        assert len(trend['data']) >= 2

    def test_detect_decline(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.margin_trend import MarginTrendAnalyzer
        calc = RealTimeMarginCalculator()
        ana = MarginTrendAnalyzer(calc)
        ana.seed_history([
            {'product_id': 'p1', 'channel': 'internal', 'margin_rate': 15.0, 'net_profit': 4500, 'selling_price': 30000},
            {'product_id': 'p1', 'channel': 'internal', 'margin_rate': 5.0, 'net_profit': 1500, 'selling_price': 30000},
        ])
        declining = ana.detect_margin_decline(threshold=5.0)
        assert any(d['product_id'] == 'p1' for d in declining)

    def test_trend_summary_structure(self):
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        from src.margin_calculator.margin_trend import MarginTrendAnalyzer
        calc = RealTimeMarginCalculator()
        ana = MarginTrendAnalyzer(calc)
        summary = ana.get_trend_summary()
        assert all(k in summary for k in ('rising', 'declining', 'stable', 'total'))


# ─── Phase110: API 테스트 ─────────────────────────────────────────────────────

class TestPh110MarginAPI:
    @pytest.fixture
    def client(self):
        from flask import Flask
        from src.api.margin_api import margin_bp
        app = Flask(__name__)
        app.register_blueprint(margin_bp)
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    def test_get_margin(self, client):
        assert client.get('/api/v1/margin/p1').status_code == 200

    def test_get_breakdown(self, client):
        assert client.get('/api/v1/margin/p1/breakdown').status_code == 200

    def test_bulk_margin(self, client):
        assert client.post('/api/v1/margin/bulk', json={}).status_code == 200

    def test_recalculate(self, client):
        assert client.post('/api/v1/margin/recalculate', json={}).status_code == 200

    def test_get_alerts(self, client):
        assert client.get('/api/v1/margin/alerts').status_code == 200

    def test_get_alert_summary(self, client):
        assert client.get('/api/v1/margin/alerts/summary').status_code == 200

    def test_simulate_price(self, client):
        resp = client.post('/api/v1/margin/simulate/price',
                           json={'product_id': 'p1', 'new_price': 30000})
        assert resp.status_code == 200

    def test_simulate_price_missing_id(self, client):
        resp = client.post('/api/v1/margin/simulate/price', json={'new_price': 30000})
        assert resp.status_code == 400

    def test_simulate_exchange_rate(self, client):
        resp = client.post('/api/v1/margin/simulate/exchange-rate',
                           json={'product_id': 'p1', 'new_rate': 1400.0})
        assert resp.status_code == 200

    def test_simulate_cost(self, client):
        resp = client.post('/api/v1/margin/simulate/cost',
                           json={'product_id': 'p1', 'cost_type': 'domestic_shipping', 'new_value': 3000})
        assert resp.status_code == 200

    def test_simulate_break_even(self, client):
        resp = client.post('/api/v1/margin/simulate/break-even', json={'product_id': 'p1'})
        assert resp.status_code == 200

    def test_simulate_target_price(self, client):
        resp = client.post('/api/v1/margin/simulate/target-price',
                           json={'product_id': 'p1', 'target_margin': 15.0})
        assert resp.status_code == 200

    def test_simulate_what_if(self, client):
        resp = client.post('/api/v1/margin/simulate/what-if',
                           json={'product_id': 'p1', 'scenarios': []})
        assert resp.status_code == 200

    def test_get_ranking(self, client):
        assert client.get('/api/v1/margin/ranking').status_code == 200

    def test_get_loss_products(self, client):
        assert client.get('/api/v1/margin/loss-products').status_code == 200

    def test_get_low_margin(self, client):
        assert client.get('/api/v1/margin/low-margin').status_code == 200

    def test_get_distribution(self, client):
        assert client.get('/api/v1/margin/distribution').status_code == 200

    def test_get_channel_profitability(self, client):
        assert client.get('/api/v1/margin/channel-profitability').status_code == 200

    def test_get_product_trend(self, client):
        assert client.get('/api/v1/margin/trend/p1').status_code == 200

    def test_get_overall_trend(self, client):
        assert client.get('/api/v1/margin/trend/overall').status_code == 200

    def test_get_channel_trend(self, client):
        assert client.get('/api/v1/margin/trend/channel/coupang').status_code == 200

    def test_get_declining(self, client):
        assert client.get('/api/v1/margin/trend/declining').status_code == 200

    def test_get_config(self, client):
        r = client.get('/api/v1/margin/config')
        assert r.status_code == 200
        assert 'config' in r.get_json()

    def test_update_config(self, client):
        assert client.put('/api/v1/margin/config',
                          json={'default_target_margin': 20.0}).status_code == 200

    def test_get_all_platform_fees(self, client):
        assert client.get('/api/v1/margin/platform-fees').status_code == 200

    def test_get_channel_fees(self, client):
        assert client.get('/api/v1/margin/platform-fees/coupang').status_code == 200

    def test_get_dashboard(self, client):
        assert client.get('/api/v1/margin/dashboard').status_code == 200

    def test_acknowledge_nonexistent(self, client):
        assert client.post('/api/v1/margin/alerts/nonexistent/acknowledge').status_code == 404


# ─── Phase110: 봇 커맨드 테스트 ──────────────────────────────────────────────

class TestPh110BotCommands:
    def test_cmd_margin_no_sku(self):
        from src.bot.margin_commands import cmd_margin
        assert '❌' in cmd_margin('')

    def test_cmd_margin_with_sku(self):
        from src.bot.margin_commands import cmd_margin
        r = cmd_margin('SKU-001')
        assert 'SKU-001' in r or '마진' in r

    def test_cmd_margin_alert(self):
        from src.bot.margin_commands import cmd_margin_alert
        r = cmd_margin_alert()
        assert '마진' in r or 'CRITICAL' in r or '현황' in r

    def test_cmd_profit_ranking_top(self):
        from src.bot.margin_commands import cmd_profit_ranking
        r = cmd_profit_ranking('top', 5)
        assert '수익성' in r or '상위' in r or '없음' in r

    def test_cmd_loss_products(self):
        from src.bot.margin_commands import cmd_loss_products
        r = cmd_loss_products()
        assert '적자' in r or '없음' in r

    def test_cmd_margin_simulate_no_sku(self):
        from src.bot.margin_commands import cmd_margin_simulate
        assert '❌' in cmd_margin_simulate('', 30000)

    def test_cmd_break_even_no_sku(self):
        from src.bot.margin_commands import cmd_break_even
        assert '❌' in cmd_break_even('')

    def test_cmd_margin_trend_no_sku(self):
        from src.bot.margin_commands import cmd_margin_trend
        assert '❌' in cmd_margin_trend('')

    def test_cmd_margin_dashboard(self):
        from src.bot.margin_commands import cmd_margin_dashboard
        r = cmd_margin_dashboard()
        assert '대시보드' in r or '마진' in r

    def test_cmd_platform_fees_all(self):
        from src.bot.margin_commands import cmd_platform_fees
        r = cmd_platform_fees()
        assert '수수료' in r

    def test_cmd_platform_fees_channel(self):
        from src.bot.margin_commands import cmd_platform_fees
        r = cmd_platform_fees('coupang')
        assert 'coupang' in r or '수수료' in r

    def test_cmd_margin_config(self):
        from src.bot.margin_commands import cmd_margin_config
        r = cmd_margin_config()
        assert '마진' in r or '설정' in r or 'target' in r
