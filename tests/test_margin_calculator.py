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
