"""구매대행 마진 계산 테스트."""

import os
import pytest
from decimal import Decimal

from src.proxy_calc.fee_table import (
    MARKET_FEES,
    SHIPPING_COSTS,
    FORWARDER_FEES,
    CUSTOMS_THRESHOLDS,
    get_commission_rate,
    get_shipping_cost,
    get_forwarder_fee,
)
from src.proxy_calc.margin_calc import ProxyMarginCalculator


FX = {
    'USDKRW': Decimal('1350'),
    'JPYKRW': Decimal('9.0'),
    'EURKRW': Decimal('1470'),
    'CNYKRW': Decimal('185'),
}


class TestFeeTable:
    def test_coupang_default_rate(self):
        assert get_commission_rate('coupang') == Decimal('10.8')

    def test_smartstore_rate(self):
        assert get_commission_rate('smartstore') == Decimal('5.5')

    def test_unknown_market_default(self):
        rate = get_commission_rate('unknown_market')
        assert rate == Decimal('10')

    def test_shipping_us_standard(self):
        assert get_shipping_cost('US', 'standard') == Decimal('15000')

    def test_shipping_jp_economy(self):
        assert get_shipping_cost('JP', 'economy') == Decimal('5000')

    def test_forwarder_jp(self):
        assert get_forwarder_fee('JP') == Decimal('2700')

    def test_forwarder_unknown_country(self):
        assert get_forwarder_fee('ZZ') == Decimal('5000')

    def test_env_override_commission(self, monkeypatch):
        monkeypatch.setenv('MARKET_FEE_COUPANG_DEFAULT', '8.5')
        assert get_commission_rate('coupang') == Decimal('8.5')

    def test_env_override_shipping(self, monkeypatch):
        monkeypatch.setenv('SHIPPING_US_STANDARD', '20000')
        assert get_shipping_cost('US', 'standard') == Decimal('20000')

    def test_env_override_forwarder(self, monkeypatch):
        monkeypatch.setenv('FORWARDER_FEE_JP', '3500')
        assert get_forwarder_fee('JP') == Decimal('3500')

    def test_customs_thresholds_exist(self):
        assert 'US' in CUSTOMS_THRESHOLDS
        assert 'JP' in CUSTOMS_THRESHOLDS
        us = CUSTOMS_THRESHOLDS['US']
        assert us['threshold_usd'] == Decimal('200')
        assert us['rate'] == Decimal('0')


class TestMarginCalculator:
    def setup_method(self):
        self.calc = ProxyMarginCalculator(fx_rates=FX)

    def test_basic_usd_calculation(self):
        result = self.calc.calculate(
            buy_price=50, currency='USD', source_country='US',
            target_market='coupang', margin_pct=25,
        )
        assert result['currency'] == 'USD'
        assert result['cost_krw'] == 67500
        assert result['sell_price_krw'] > result['total_cost_krw']
        assert result['net_profit_krw'] > 0
        assert result['commission_pct'] == 10.8

    def test_jpy_calculation(self):
        result = self.calc.calculate(
            buy_price=5000, currency='JPY', source_country='JP',
            target_market='smartstore', margin_pct=30,
        )
        assert result['cost_krw'] == 45000
        assert result['commission_pct'] == 5.5
        assert result['sell_price_krw'] > 0

    def test_cny_calculation(self):
        result = self.calc.calculate(
            buy_price=200, currency='CNY', source_country='CN',
            target_market='coupang', margin_pct=25,
        )
        assert result['cost_krw'] == 37000
        assert result['sell_price_krw'] > 0

    def test_customs_exempt_us_fta(self):
        """미국 $200 이하 FTA 면세."""
        result = self.calc.calculate(
            buy_price=100, currency='USD', source_country='US',
        )
        assert result['customs_duty_krw'] == 0

    def test_customs_charged_us(self):
        """미국 $200 초과 — 면세 아님 (US rate=0 이므로 여전히 0)."""
        result = self.calc.calculate(
            buy_price=250, currency='USD', source_country='US',
        )
        # US는 FTA rate=0 이므로 금액과 무관하게 관세 0
        assert result['customs_duty_krw'] == 0

    def test_customs_charged_jp(self):
        """일본 15만엔 → 135만원 > 면세기준 → 관세 부과."""
        result = self.calc.calculate(
            buy_price=150000, currency='JPY', source_country='JP',
        )
        assert result['customs_duty_krw'] > 0

    def test_extra_cost_included(self):
        result = self.calc.calculate(
            buy_price=50, currency='USD', source_country='US',
            extra_cost_krw=5000,
        )
        assert result['extra_cost_krw'] == 5000
        assert result['subtotal_krw'] > 67500 + 5000

    def test_different_shipping_methods(self):
        std = self.calc.calculate(buy_price=50, currency='USD', shipping_method='standard')
        exp = self.calc.calculate(buy_price=50, currency='USD', shipping_method='express')
        assert exp['shipping_fee_krw'] > std['shipping_fee_krw']
        assert exp['sell_price_krw'] > std['sell_price_krw']

    def test_net_margin_positive(self):
        result = self.calc.calculate(buy_price=30, currency='USD', margin_pct=25)
        assert result['net_margin_pct'] > 0

    def test_result_keys(self):
        result = self.calc.calculate(buy_price=50, currency='USD')
        expected_keys = [
            'buy_price', 'currency', 'cost_krw', 'forwarder_fee_krw',
            'shipping_fee_krw', 'extra_cost_krw', 'subtotal_krw',
            'customs_duty_krw', 'total_cost_krw', 'commission_pct',
            'margin_pct', 'sell_price_krw', 'commission_krw',
            'net_profit_krw', 'net_margin_pct',
        ]
        for key in expected_keys:
            assert key in result, f'{key} missing from result'


class TestReverseCalculation:
    def setup_method(self):
        self.calc = ProxyMarginCalculator(fx_rates=FX)

    def test_reverse_basic(self):
        result = self.calc.reverse_calculate(
            target_sell_price=100000, currency='USD',
            target_market='coupang',
        )
        assert result['target_sell_price_krw'] == 100000
        assert result['max_buy_price'] > 0
        assert result['currency'] == 'USD'

    def test_reverse_yields_reasonable_buy_price(self):
        result = self.calc.reverse_calculate(
            target_sell_price=200000, currency='USD',
            target_market='smartstore',
        )
        assert result['max_buy_price'] < 200000 / 1350


class TestCompareMarkets:
    def setup_method(self):
        self.calc = ProxyMarginCalculator(fx_rates=FX)

    def test_compare_default_markets(self):
        results = self.calc.compare_markets(buy_price=50, currency='USD')
        assert len(results) == 5
        for r in results:
            assert 'market' in r
            assert 'sell_price_krw' in r

    def test_compare_custom_markets(self):
        results = self.calc.compare_markets(
            buy_price=50, currency='USD',
            markets=['coupang', 'smartstore'],
        )
        assert len(results) == 2

    def test_compare_sorted_by_profit(self):
        results = self.calc.compare_markets(buy_price=50, currency='USD')
        profits = [r['net_profit_krw'] for r in results]
        assert profits == sorted(profits, reverse=True)


class TestBatchCalculation:
    def setup_method(self):
        self.calc = ProxyMarginCalculator(fx_rates=FX)

    def test_batch_multiple_items(self):
        items = [
            {'buy_price': 30, 'currency': 'USD'},
            {'buy_price': 5000, 'currency': 'JPY', 'source_country': 'JP'},
            {'buy_price': 100, 'currency': 'CNY', 'source_country': 'CN'},
        ]
        results = self.calc.batch_calculate(items)
        assert len(results) == 3
        for r in results:
            assert 'sell_price_krw' in r or 'error' in r

    def test_batch_with_error(self):
        items = [
            {'buy_price': 30, 'currency': 'USD'},
            {'buy_price': 50, 'currency': 'INVALID_CURRENCY'},
        ]
        results = self.calc.batch_calculate(items)
        assert len(results) == 2
        assert 'sell_price_krw' in results[0]
        assert 'error' in results[1]
