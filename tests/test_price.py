"""src/price.py 단위 테스트"""
from decimal import Decimal
import pytest
import sys
import os

# 패키지 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.price import (  # noqa: E402
    DEFAULT_FX_RATES,
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
# 판매가 = 실수령 마진 기준 (오너 결정 2026-09-20 · 볼트 정책)
#
#   판매가 = (랜딩코스트 + 국내배송비) ÷ (1 − 마켓수수료율 − 목표마진율)
#
# 예전엔 markup(`랜딩코스트 × (1+마진율)`)이었다. 그 식으로 매긴 카나리 1호는
# 수수료·국내배송을 빼면 **실마진 −4.9%**였다 — 팔릴수록 손해였다.
# ──────────────────────────────────────────────────────────

COUPANG_COMMISSION = Decimal('10.8')     # 볼트 실측
DOMESTIC_SHIP = Decimal('3000')          # 볼트 정책


def _expected_sell(landed, margin_pct=Decimal('22')):
    denom = (Decimal('100') - COUPANG_COMMISSION - Decimal(str(margin_pct))) / Decimal('100')
    return round((landed + DOMESTIC_SHIP) / denom, 2)


class TestCalcLandedCost:
    """`calc_landed_cost`는 **옛 이름**이고, 이제 `calc_sell_price`(쿠팡 기준)를 부른다."""

    def test_below_customs_threshold(self):
        """원가 KRW 환산액이 면세 기준(15만원) 이하: 관부가세 0%"""
        # JPY 10000 → 90000 KRW (< 150000) → 관부가세 없음
        cost_krw = Decimal('10000') * Decimal('9.0')        # 90000
        fwd_krw = Decimal('300') * Decimal('9.0')           # 2700
        landed = cost_krw + fwd_krw + Decimal('12000')      # 104700

        result = calc_landed_cost(
            10000, 'JPY', 22,
            fx_rates=FX,
            forwarder_fee=300,
            shipping_fee=12000,
            customs_threshold_krw=150000,
            market='coupang',
        )
        assert result == _expected_sell(landed)

    def test_above_customs_threshold(self):
        """원가 KRW 환산액이 면세 기준(15만원) 초과: 관부가세 20% 자동 적용"""
        cost_krw = Decimal('20000') * Decimal('9.0')        # 180000
        fwd_krw = Decimal('300') * Decimal('9.0')           # 2700
        landed = (cost_krw + fwd_krw + Decimal('12000')) * Decimal('1.20')

        result = calc_landed_cost(
            20000, 'JPY', 22,
            fx_rates=FX,
            forwarder_fee=300,
            shipping_fee=12000,
            customs_threshold_krw=150000,
            customs_rate=Decimal('0.20'),
            market='coupang',
        )
        assert result == _expected_sell(landed)

    def test_explicit_customs_rate_zero(self):
        """customs_rate=0 을 명시하면 관부가세 미부과"""
        landed = Decimal('20000') * Decimal('9.0') + Decimal('300') * Decimal('9.0') + Decimal('12000')
        result = calc_landed_cost(
            20000, 'JPY', 22,
            fx_rates=FX, forwarder_fee=300, shipping_fee=12000, customs_rate=0,
            market='coupang',
        )
        assert result == _expected_sell(landed)

    def test_eur_product(self):
        """EUR 원가 상품"""
        landed = Decimal('100') * Decimal('1470') + Decimal('300') * Decimal('9.0') + Decimal('12000')
        result = calc_landed_cost(
            100, 'EUR', 22,
            fx_rates=FX, forwarder_fee=300, shipping_fee=12000,
            customs_threshold_krw=150000, market='coupang',
        )
        assert result == _expected_sell(landed)

    def test_the_target_margin_is_what_actually_remains(self):
        """★★ **이 계약이 식의 뜻이다** — 판매가에서 수수료·배송을 빼면 정확히 목표마진.

        오너 지시: 「판매가에서 수수료·배송을 빼면 정확히 목표마진」.
        """
        from src.price import landed_cost_krw, net_margin_pct

        landed = landed_cost_krw(10000, 'JPY', fx_rates=FX, forwarder_fee=300,
                                 shipping_fee=12000, customs_threshold_krw=150000)
        sell = calc_landed_cost(10000, 'JPY', 22, fx_rates=FX, forwarder_fee=300,
                                shipping_fee=12000, customs_threshold_krw=150000,
                                market='coupang')
        got = net_margin_pct(sell, landed, 'coupang')
        assert abs(got - Decimal('22')) < Decimal('0.01'), got

    def test_an_unknown_market_commission_refuses_to_price(self):
        """★★ **모르면 지어내지 않는다** — 수수료율이 없으면 값을 내지 않는다."""
        from src.price import PricingError, calc_sell_price

        with pytest.raises(PricingError, match='판매수수료율'):
            calc_sell_price(100, 'USD', 'some_new_market', 22, fx_rates=FX)

    def test_an_impossible_target_is_refused(self):
        """★ 마진+수수료가 100%를 넘으면 판매가가 없다 — 큰 수를 내놓지 않는다."""
        from src.price import PricingError, calc_sell_price

        with pytest.raises(PricingError, match='100%'):
            calc_sell_price(100, 'USD', 'coupang', 92, fx_rates=FX)

    def test_a_measured_commission_can_be_supplied_by_env(self, monkeypatch):
        """★ 오너가 실측값을 넣으면 그 마켓도 값이 난다."""
        from src.price import calc_sell_price, commission_pct

        monkeypatch.setenv('MARKET_COMMISSION_PCT_SHOPIFY', '2.9')
        rate, why = commission_pct('shopify')
        assert rate == Decimal('2.9') and not why
        assert calc_sell_price(100, 'USD', 'shopify', 22, fx_rates=FX) > 0


# ──────────────────────────────────────────────────────────
# 지원하지 않는 통화 오류 처리
# ──────────────────────────────────────────────────────────

class TestUnsupportedCurrency:
    def test_unknown_currency_raises(self):
        with pytest.raises(ValueError, match='지원하지 않는 통화'):
            calc_price(100, 'GBP', 1350, 0, 'KRW', fx_rates=FX)
