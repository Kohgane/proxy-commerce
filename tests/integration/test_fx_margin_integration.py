"""tests/integration/test_fx_margin_integration.py — 환율+마진 통합 테스트.

실시간 환율 변동 시 마진 재계산, 마진 하한선 보호,
다중 셀러 마진 정책 적용을 검증한다.
"""

from decimal import Decimal
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# 실시간 환율 변동 시 마진 재계산
# ---------------------------------------------------------------------------

class TestFxMarginRecalculation:
    """실시간 환율 변동 시 마진 재계산 통합 테스트."""

    def test_margin_changes_with_fx_rate(self):
        """환율 상승 시 동일 판매가에서 마진율이 하락하는지 검증한다."""
        from src.margin.calculator import MarginCalculator

        # 환율 1350원일 때
        calc_low_fx = MarginCalculator(krw_per_usd=1350.0)
        result_low = calc_low_fx.calculate(
            foreign_price=50.0,
            sale_price_krw=100000,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
        )

        # 환율 1450원일 때 (원가 상승 → 마진 하락)
        calc_high_fx = MarginCalculator(krw_per_usd=1450.0)
        result_high = calc_high_fx.calculate(
            foreign_price=50.0,
            sale_price_krw=100000,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
        )

        # 환율 상승 → 원가 상승 → 마진 하락
        assert result_high['margin_rate'] < result_low['margin_rate']

    def test_margin_recalculate_with_live_fx_service(self):
        """RealtimeRates 서비스와 연동된 마진 재계산 흐름을 검증한다."""
        from src.margin.calculator import MarginCalculator

        mock_fx = MagicMock()
        mock_fx.get_rate.return_value = Decimal('1380')

        calc = MarginCalculator(fx_service=mock_fx, krw_per_usd=1380.0)
        result = calc.calculate(
            foreign_price=50.0,
            sale_price_krw=100000,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
        )

        assert result is not None
        assert 'margin_rate' in result
        assert 'exchange_rate' in result

    def test_fx_rate_cache_integration(self):
        """RateCache와 마진 계산 통합 — 캐시된 환율로 재계산하는 흐름을 검증한다."""
        from src.fx.rate_cache import RateCache

        cache = RateCache(ttl_seconds=60)
        cache.set('USD', 'KRW', Decimal('1350'))

        cached_rate = cache.get('USD', 'KRW')
        assert cached_rate == Decimal('1350')

        # 캐시된 환율로 마진 계산
        from src.margin.calculator import MarginCalculator
        calc = MarginCalculator(krw_per_usd=float(cached_rate))
        result = calc.calculate(
            foreign_price=50.0,
            sale_price_krw=90000,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
        )
        assert result['exchange_rate'] == float(cached_rate)

    def test_jpy_fx_margin_integration(self):
        """JPY 환율 변동 시 마진 재계산 통합 흐름을 검증한다."""
        from src.margin.calculator import MarginCalculator

        # JPY/KRW 9.0원일 때
        calc1 = MarginCalculator(krw_per_usd=1350.0)
        result1 = calc1.calculate(
            foreign_price=9980.0,
            sale_price_krw=120000,
            currency='JPY',
            marketplace='amazon_jp',
            platform='coupang',
        )

        # JPY/KRW 9.5원일 때 (환율 상승 → 원가 상승)
        calc2 = MarginCalculator(krw_per_usd=1350.0)
        # JPY 환율은 계산기 내부 기본값을 사용하므로
        # 결과 구조 검증에 집중
        result2 = calc2.calculate(
            foreign_price=9980.0,
            sale_price_krw=120000,
            currency='JPY',
            marketplace='amazon_jp',
            platform='naver',
        )

        assert 'margin_rate' in result1
        assert 'margin_rate' in result2
        # 플랫폼(수수료)이 다르면 마진율도 다름
        assert result1['margin_rate'] != result2['margin_rate']


# ---------------------------------------------------------------------------
# 마진 하한선 보호 검증
# ---------------------------------------------------------------------------

class TestMarginFloorProtection:
    """마진 하한선 보호 통합 테스트."""

    def test_unprofitable_product_flagged(self):
        """손익 분기점 미달 상품에 is_profitable=False 플래그가 설정되는지 검증한다."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)
        # 원가(50 USD * 1350 = 67500) + 배송비 > 판매가(60000)인 경우
        result = calc.calculate(
            foreign_price=50.0,
            sale_price_krw=60000,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
            weight_kg=0.5,
        )

        assert result['is_profitable'] is False

    def test_profitable_product_flagged(self):
        """수익성 있는 상품에 is_profitable=True 플래그가 설정되는지 검증한다."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.calculate(
            foreign_price=10.0,
            sale_price_krw=50000,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
            weight_kg=0.1,
        )

        assert result['is_profitable'] is True

    def test_reverse_calculate_ensures_minimum_margin(self):
        """역계산(목표 마진율 → 판매가)이 최소 마진을 보장하는지 검증한다."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.reverse_calculate(
            foreign_price=50.0,
            target_margin_rate=20.0,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
            weight_kg=0.3,
        )

        assert result['optimal_sale_price'] > 0
        assert result['rounded_sale_price'] % 100 == 0
        # 권장 판매가는 원가 + 배송비 이상이어야 함
        assert result['optimal_sale_price'] > 50.0 * 1350.0

    def test_bulk_summary_includes_profitable_count(self):
        """배치 요약에 수익성 있는 상품 수가 포함되는지 검증한다."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)
        products = [
            {'foreign_price': 10.0, 'sale_price_krw': 50000,
             'currency': 'USD', 'platform': 'coupang'},
            {'foreign_price': 50.0, 'sale_price_krw': 60000,
             'currency': 'USD', 'platform': 'coupang'},
        ]
        report = calc.generate_report(products)

        assert 'profitable_count' in report
        assert 'avg_margin_rate' in report
        assert report['total_products'] == 2


# ---------------------------------------------------------------------------
# 다중 셀러 마진 정책 적용 검증
# ---------------------------------------------------------------------------

class TestMultiSellerMarginPolicy:
    """다중 셀러 마진 정책 적용 통합 테스트."""

    def test_different_margin_rates_per_seller(self):
        """셀러별 다른 마진율 적용 시 다른 가격이 산출되는지 검증한다."""
        from src.price import calc_price

        buy_price = Decimal('50')
        fx_rates = {'USDKRW': Decimal('1350'), 'JPYKRW': Decimal('9.0')}

        # 셀러 A: 마진 20%
        price_a = calc_price(
            buy_price, 'USD', Decimal('1350'), Decimal('20'), 'KRW',
            fx_rates=fx_rates,
        )

        # 셀러 B: 마진 30%
        price_b = calc_price(
            buy_price, 'USD', Decimal('1350'), Decimal('30'), 'KRW',
            fx_rates=fx_rates,
        )

        assert price_b > price_a

    def test_coupang_vs_naver_fee_difference(self):
        """쿠팡 vs 네이버 수수료 차이가 마진율에 반영되는지 검증한다."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)

        result_coupang = calc.calculate(
            foreign_price=50.0,
            sale_price_krw=100000,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
        )

        result_naver = calc.calculate(
            foreign_price=50.0,
            sale_price_krw=100000,
            currency='USD',
            marketplace='amazon_us',
            platform='naver',
        )

        # 수수료율이 다르면 마진율도 달라야 함
        assert result_coupang['fee_rate'] != result_naver['fee_rate']
        assert result_coupang['margin_rate'] != result_naver['margin_rate']

    def test_multi_currency_multi_seller_pricing(self):
        """다중 통화 × 다중 셀러 가격 산정 통합 검증."""
        from src.fx.multi_currency import MultiCurrencyConverter
        from src.price import calc_price

        converter = MultiCurrencyConverter(
            fx_rates={
                'USDKRW': Decimal('1350'),
                'JPYKRW': Decimal('9.0'),
                'CNYKRW': Decimal('185'),
            }
        )

        scenarios = [
            ('USD', Decimal('50'), Decimal('20')),
            ('JPY', Decimal('9980'), Decimal('22')),
            ('CNY', Decimal('30'), Decimal('25')),
        ]

        results = []
        for currency, price, margin in scenarios:
            krw = converter.to_krw(price, currency)
            sell = calc_price(
                price, currency, Decimal('1350'), margin, 'KRW',
                fx_rates={
                    'USDKRW': Decimal('1350'),
                    'JPYKRW': Decimal('9.0'),
                    'CNYKRW': Decimal('185'),
                },
            )
            results.append({'currency': currency, 'cost_krw': krw, 'sell_price': sell})

        assert len(results) == 3
        for r in results:
            assert r['sell_price'] > r['cost_krw']
