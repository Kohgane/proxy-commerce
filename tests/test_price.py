"""src/price.py 단위 테스트"""
from decimal import Decimal
import pytest
import sys
import os

# 패키지 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.price import (
    DEFAULT_FX_RATES,
    _build_fx_rates,
    _to_krw,
    _from_krw,
    calc_price,
    calc_landed_cost,
)

# 테스트용 고정 환율
FX = {
    'USDKRW': Decimal('1350'),
    'JPYKRW': Decimal('9.0'),
    'EURKRW': Decimal('1470'),
}


# ──────────────────────────────────────────────────────────
# DEFAULT_FX_RATES 구조 확인
# ──────────────────────────────────────────────────────────

class TestDefaultFxRates:
    def test_keys_exist(self):
        assert 'USDKRW' in DEFAULT_FX_RATES
        assert 'JPYKRW' in DEFAULT_FX_RATES
        assert 'EURKRW' in DEFAULT_FX_RATES

    def test_values_are_decimal(self):
        for v in DEFAULT_FX_RATES.values():
            assert isinstance(v, Decimal)


# ──────────────────────────────────────────────────────────
# 하위호환 테스트: 기존 calc_price 시그니처 그대로 동작
# ──────────────────────────────────────────────────────────

class TestCalcPriceBackwardCompat:
    def test_usd_to_krw(self):
        # $100, 22% 마진, 1350 환율 → 100 × 1350 × 1.22 = 164700
        result = calc_price(100, 'USD', 1350, 22, 'KRW')
        assert result == Decimal('164700.00')

    def test_krw_to_usd(self):
        # ₩135000, 0% 마진, 1350 환율 → 135000 / 1350 = 100
        result = calc_price(135000, 'KRW', 1350, 0, 'USD')
        assert result == Decimal('100.00')

    def test_krw_to_krw(self):
        # ₩10000, 10% 마진 → 11000
        result = calc_price(10000, 'KRW', 1350, 10, 'KRW')
        assert result == Decimal('11000.00')


# ──────────────────────────────────────────────────────────
# JPY→KRW 변환 테스트
# ──────────────────────────────────────────────────────────

class TestJpyToKrw:
    def test_jpy_to_krw_no_margin(self):
        # ¥30,000, 0% 마진, JPYKRW=9.0 → 30000 × 9 = 270000
        result = calc_price(30000, 'JPY', 1350, 0, 'KRW', fx_rates=FX)
        assert result == Decimal('270000.00')

    def test_jpy_to_krw_with_margin(self):
        # ¥30,000, 22% 마진 → 270000 × 1.22 = 329400
        result = calc_price(30000, 'JPY', 1350, 22, 'KRW', fx_rates=FX)
        assert result == Decimal('329400.00')

    def test_jpy_to_usd(self):
        # ¥13500, 0% 마진 → 13500 × 9 = 121500 KRW → / 1350 = 90 USD
        result = calc_price(13500, 'JPY', 1350, 0, 'USD', fx_rates=FX)
        assert result == Decimal('90.00')


# ──────────────────────────────────────────────────────────
# EUR→KRW 변환 테스트
# ──────────────────────────────────────────────────────────

class TestEurToKrw:
    def test_eur_to_krw_no_margin(self):
        # €150, 0% 마진, EURKRW=1470 → 150 × 1470 = 220500
        result = calc_price(150, 'EUR', 1350, 0, 'KRW', fx_rates=FX)
        assert result == Decimal('220500.00')

    def test_eur_to_krw_with_margin(self):
        # €150, 10% 마진 → 220500 × 1.10 = 242550
        result = calc_price(150, 'EUR', 1350, 10, 'KRW', fx_rates=FX)
        assert result == Decimal('242550.00')


# ──────────────────────────────────────────────────────────
# EUR→USD 변환 테스트
# ──────────────────────────────────────────────────────────

class TestEurToUsd:
    def test_eur_to_usd_no_margin(self):
        # €100, 0% 마진 → 100 × 1470 = 147000 KRW → / 1350 ≈ 108.89 USD
        result = calc_price(100, 'EUR', 1350, 0, 'USD', fx_rates=FX)
        expected = (Decimal('100') * Decimal('1470') / Decimal('1350')).quantize(Decimal('0.01'))
        # round(..., 2) 결과와 비교
        assert result == round(expected, 2)


# ──────────────────────────────────────────────────────────
# calc_landed_cost 테스트
# ──────────────────────────────────────────────────────────

class TestCalcLandedCost:
    def test_below_customs_threshold(self):
        """원가 KRW 환산액이 면세 기준(15만원) 이하: 관부가세 0%"""
        # JPY 10000 → 90000 KRW (< 150000) → 관부가세 없음
        # (90000 + 300 × 9 + 12000) × 1.0 × 1.22
        cost_krw = Decimal('10000') * Decimal('9.0')        # 90000
        fwd_krw = Decimal('300') * Decimal('9.0')           # 2700
        shipping = Decimal('12000')
        total = cost_krw + fwd_krw + shipping               # 104700
        expected = round(total * Decimal('1.22'), 2)        # 127734.00

        result = calc_landed_cost(
            10000, 'JPY', 22,
            fx_rates=FX,
            forwarder_fee=300,
            shipping_fee=12000,
            customs_threshold_krw=150000,
        )
        assert result == expected

    def test_above_customs_threshold(self):
        """원가 KRW 환산액이 면세 기준(15만원) 초과: 관부가세 20% 자동 적용"""
        # JPY 20000 → 180000 KRW (> 150000) → 관부가세 20%
        cost_krw = Decimal('20000') * Decimal('9.0')        # 180000
        fwd_krw = Decimal('300') * Decimal('9.0')           # 2700
        shipping = Decimal('12000')
        total = cost_krw + fwd_krw + shipping               # 194700
        expected = round(total * Decimal('1.20') * Decimal('1.22'), 2)

        result = calc_landed_cost(
            20000, 'JPY', 22,
            fx_rates=FX,
            forwarder_fee=300,
            shipping_fee=12000,
            customs_threshold_krw=150000,
            customs_rate=Decimal('0.20'),
        )
        assert result == expected

    def test_explicit_customs_rate_zero(self):
        """customs_rate=0 을 명시하면 관부가세 미부과"""
        result_no_customs = calc_landed_cost(
            20000, 'JPY', 22,
            fx_rates=FX,
            forwarder_fee=300,
            shipping_fee=12000,
            customs_rate=0,
        )
        cost_krw = Decimal('20000') * Decimal('9.0')
        fwd_krw = Decimal('300') * Decimal('9.0')
        shipping = Decimal('12000')
        total = cost_krw + fwd_krw + shipping
        expected = round(total * Decimal('1.22'), 2)
        assert result_no_customs == expected

    def test_eur_product(self):
        """EUR 원가 상품의 landed cost"""
        # €100 → 147000 KRW, 관부가세 없음 (147000 < 150000)
        cost_krw = Decimal('100') * Decimal('1470')         # 147000
        fwd_krw = Decimal('300') * Decimal('9.0')           # 2700
        shipping = Decimal('12000')
        total = cost_krw + fwd_krw + shipping               # 161700
        expected = round(total * Decimal('1.22'), 2)        # 197274.00

        result = calc_landed_cost(
            100, 'EUR', 22,
            fx_rates=FX,
            forwarder_fee=300,
            shipping_fee=12000,
            customs_threshold_krw=150000,
        )
        assert result == expected


# ──────────────────────────────────────────────────────────
# 지원하지 않는 통화 오류 처리
# ──────────────────────────────────────────────────────────

class TestUnsupportedCurrency:
    def test_unknown_currency_raises(self):
        with pytest.raises(ValueError, match='지원하지 않는 통화'):
            calc_price(100, 'GBP', 1350, 0, 'KRW', fx_rates=FX)
