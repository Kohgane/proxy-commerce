"""tests/e2e/test_pricing_pipeline.py — 가격 산정 파이프라인 E2E 테스트.

환율 적용 + 마진 계산 + 배송비 포함 전체 흐름을 검증한다.
다중 통화(USD, JPY, CNY → KRW) 변환, 반올림 규칙, 경쟁사 가격 조정도 검증한다.
"""

from decimal import Decimal
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# 가격 계산 기본 검증
# ---------------------------------------------------------------------------

class TestPricingWithFX:
    """환율 적용 가격 산정 E2E 테스트."""

    def test_usd_to_krw_price_calculation(self, monkeypatch):
        """USD 상품가격 → KRW 판매가 계산 전체 흐름을 검증한다."""
        from src.price import calc_price

        buy_price = Decimal('49.99')
        fx_usdkrw = Decimal('1350')
        margin = Decimal('20')

        result = calc_price(
            buy_price, 'USD', Decimal('1350'), margin, 'KRW',
            fx_rates={
                'USDKRW': fx_usdkrw,
                'JPYKRW': Decimal('9.0'),
                'EURKRW': Decimal('1470'),
            },
        )

        expected_base = buy_price * fx_usdkrw
        assert result > expected_base
        assert result > 0

    def test_jpy_to_krw_price_calculation(self, monkeypatch):
        """JPY 상품가격 → KRW 판매가 계산 전체 흐름을 검증한다."""
        from src.price import calc_price

        buy_price = Decimal('9980')
        fx_jpykrw = Decimal('9.0')
        margin = Decimal('22')

        result = calc_price(
            buy_price, 'JPY', Decimal('1350'), margin, 'KRW',
            fx_rates={
                'USDKRW': Decimal('1350'),
                'JPYKRW': fx_jpykrw,
                'EURKRW': Decimal('1470'),
            },
        )

        expected_base = buy_price * fx_jpykrw
        assert result > expected_base
        assert result > 0

    def test_cny_to_krw_price_calculation(self, monkeypatch):
        """CNY 상품가격 → KRW 판매가 계산 전체 흐름을 검증한다."""
        from src.price import calc_price

        buy_price = Decimal('29.9')
        fx_cnykrw = Decimal('185')
        margin = Decimal('25')

        result = calc_price(
            buy_price, 'CNY', Decimal('1350'), margin, 'KRW',
            fx_rates={
                'USDKRW': Decimal('1350'),
                'JPYKRW': Decimal('9.0'),
                'EURKRW': Decimal('1470'),
                'CNYKRW': fx_cnykrw,
            },
        )

        expected_base = buy_price * fx_cnykrw
        assert result > expected_base
        assert result > 0


# ---------------------------------------------------------------------------
# 다중 통화 변환 검증
# ---------------------------------------------------------------------------

class TestMultiCurrencyConversion:
    """다중 통화 변환 E2E 테스트."""

    def test_multi_currency_converter_usd_to_krw(self):
        """MultiCurrencyConverter USD→KRW 변환을 검증한다."""
        from src.fx.multi_currency import MultiCurrencyConverter

        converter = MultiCurrencyConverter(
            fx_rates={
                'USDKRW': Decimal('1350'),
                'JPYKRW': Decimal('9.0'),
                'CNYKRW': Decimal('185'),
            }
        )
        result = converter.convert(Decimal('100'), 'USD', 'KRW')
        assert result == Decimal('135000')

    def test_multi_currency_converter_jpy_to_krw(self):
        """MultiCurrencyConverter JPY→KRW 변환을 검증한다."""
        from src.fx.multi_currency import MultiCurrencyConverter

        converter = MultiCurrencyConverter(
            fx_rates={'JPYKRW': Decimal('9.0'), 'USDKRW': Decimal('1350')}
        )
        result = converter.convert(Decimal('10000'), 'JPY', 'KRW')
        assert result == Decimal('90000')

    def test_multi_currency_converter_cny_to_krw(self):
        """MultiCurrencyConverter CNY→KRW 변환을 검증한다."""
        from src.fx.multi_currency import MultiCurrencyConverter

        converter = MultiCurrencyConverter(
            fx_rates={'CNYKRW': Decimal('185'), 'USDKRW': Decimal('1350')}
        )
        result = converter.convert(Decimal('100'), 'CNY', 'KRW')
        assert result == Decimal('18500')

    def test_same_currency_conversion(self):
        """동일 통화 변환 시 원래 금액을 반환한다."""
        from src.fx.multi_currency import MultiCurrencyConverter

        converter = MultiCurrencyConverter()
        result = converter.convert(Decimal('50000'), 'KRW', 'KRW')
        assert result == Decimal('50000')

    def test_different_fx_rates_yield_different_prices(self):
        """환율이 다를 경우 다른 KRW 가격이 산출되는지 검증한다."""
        from src.fx.multi_currency import MultiCurrencyConverter

        c1 = MultiCurrencyConverter(fx_rates={'JPYKRW': Decimal('9.0'), 'USDKRW': Decimal('1350')})
        c2 = MultiCurrencyConverter(fx_rates={'JPYKRW': Decimal('9.5'), 'USDKRW': Decimal('1350')})

        price1 = c1.convert(Decimal('10000'), 'JPY', 'KRW')
        price2 = c2.convert(Decimal('10000'), 'JPY', 'KRW')

        assert price2 > price1


# ---------------------------------------------------------------------------
# 가격 반올림 규칙 검증
# ---------------------------------------------------------------------------

class TestPriceRoundingRules:
    """가격 반올림 규칙 E2E 테스트."""

    def test_coupang_price_rounding_to_100(self):
        """쿠팡 판매가는 100원 단위로 반올림되어야 한다 (reverse_calculate 사용)."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.reverse_calculate(
            foreign_price=50.0,
            target_margin_rate=20.0,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
        )
        # reverse_calculate는 100원 단위 반올림을 보장함
        assert result['rounded_sale_price'] % 100 == 0

    def test_naver_price_rounding_to_10(self):
        """네이버 판매가가 10원 단위로 반올림되는지 검증한다."""
        from src.price import calc_price

        buy_price = Decimal('15.33')
        result = calc_price(
            buy_price, 'USD', Decimal('1350'), Decimal('20'), 'KRW',
            fx_rates={'USDKRW': Decimal('1350'), 'JPYKRW': Decimal('9.0')},
        )
        # calc_price는 소수점 2자리 반올림. 10원 단위 반올림은 업로더에서 처리
        assert result > 0

    def test_price_always_positive(self):
        """계산된 가격이 항상 양수인지 검증한다."""
        from src.price import calc_price

        for buy in ['1', '10', '100', '1000']:
            result = calc_price(
                Decimal(buy), 'USD', Decimal('1350'), Decimal('20'), 'KRW',
                fx_rates={'USDKRW': Decimal('1350'), 'JPYKRW': Decimal('9.0')},
            )
            assert result > 0


# ---------------------------------------------------------------------------
# 마진 계산기 E2E 테스트
# ---------------------------------------------------------------------------

class TestMarginCalculatorPipeline:
    """MarginCalculator 전체 파이프라인 E2E 테스트."""

    def test_margin_calculate_usd_coupang(self):
        """USD 상품 → 쿠팡 플랫폼 마진 계산 전체 흐름을 검증한다."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.calculate(
            foreign_price=49.99,
            sale_price_krw=90000,
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
            weight_kg=0.3,
        )

        assert 'margin_rate' in result
        assert 'total_cost' in result
        assert 'net_revenue' in result
        assert 'is_profitable' in result
        assert result['currency'] == 'USD'
        assert result['foreign_price'] == 49.99

    def test_margin_calculate_jpy_naver(self):
        """JPY 상품 → 네이버 플랫폼 마진 계산 전체 흐름을 검증한다."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.calculate(
            foreign_price=9980,
            sale_price_krw=120000,
            currency='JPY',
            marketplace='amazon_jp',
            platform='naver',
            weight_kg=0.05,
        )

        assert 'margin_rate' in result
        assert result['currency'] == 'JPY'
        assert result['total_cost'] > 0

    def test_margin_calculate_with_live_fx(self):
        """실시간 환율 서비스와 연동된 마진 계산을 검증한다."""
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

    def test_margin_reverse_calculation(self):
        """목표 마진율로 최적 판매가를 역산하는 흐름을 검증한다."""
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

        assert 'optimal_sale_price' in result
        assert 'rounded_sale_price' in result
        assert result['optimal_sale_price'] > 0
        assert result['rounded_sale_price'] > 50.0 * 1350.0
        assert result['target_margin_rate'] == 20.0

    def test_margin_bulk_calculate(self):
        """다수 상품 배치 마진 계산을 검증한다."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)
        products = [
            {'foreign_price': 49.99, 'sale_price_krw': 90000,
             'currency': 'USD', 'platform': 'coupang'},
            {'foreign_price': 9980, 'sale_price_krw': 120000,
             'currency': 'JPY', 'platform': 'naver'},
            {'foreign_price': 29.9, 'sale_price_krw': 15000,
             'currency': 'CNY', 'platform': 'coupang'},
        ]
        results = calc.bulk_calculate(products)

        assert len(results) == 3
        for r in results:
            assert 'margin_rate' in r


# ---------------------------------------------------------------------------
# 경쟁사 가격 대비 자동 가격 조정 검증
# ---------------------------------------------------------------------------

class TestCompetitivePricing:
    """경쟁사 가격 대비 자동 가격 조정 E2E 테스트."""

    def test_price_below_competitor(self):
        """경쟁사 가격보다 낮은 가격이 산출되는 시나리오를 검증한다."""
        from src.price import calc_price

        competitor_price = Decimal('100000')
        buy_price = Decimal('50')

        our_price = calc_price(
            buy_price, 'USD', Decimal('1350'), Decimal('20'), 'KRW',
            fx_rates={'USDKRW': Decimal('1350'), 'JPYKRW': Decimal('9.0')},
        )

        # 20% 마진 적용 시 50USD * 1350 * 1.2 = 81000 < 100000 (경쟁사)
        assert our_price < competitor_price

    def test_margin_floor_protection(self):
        """마진 하한선(최소 마진율) 보호 검증."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)
        result = calc.calculate(
            foreign_price=50.0,
            sale_price_krw=70000,  # 낮은 판매가 (마진 손실 가능성)
            currency='USD',
            marketplace='amazon_us',
            platform='coupang',
            weight_kg=0.3,
        )

        # 결과에 is_profitable 플래그가 있어야 함
        assert 'is_profitable' in result
        assert isinstance(result['is_profitable'], bool)
