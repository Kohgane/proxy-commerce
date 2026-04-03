"""tests/test_multicurrency.py — Phase 45: 멀티통화 시스템 테스트."""
import pytest


class TestCurrencyManager:
    def setup_method(self):
        from src.multicurrency.currency_manager import CurrencyManager
        self.mgr = CurrencyManager()

    def test_default_currencies_registered(self):
        currencies = self.mgr.list_all()
        codes = [c['code'] for c in currencies]
        assert 'KRW' in codes
        assert 'USD' in codes
        assert 'JPY' in codes

    def test_base_currency_default(self):
        assert self.mgr.base_currency == 'KRW'

    def test_set_base_currency(self):
        self.mgr.set_base_currency('USD')
        assert self.mgr.base_currency == 'USD'

    def test_set_invalid_base_currency(self):
        with pytest.raises(ValueError):
            self.mgr.set_base_currency('XYZ')

    def test_register_new_currency(self):
        self.mgr.register('SGD', name='싱가포르 달러', symbol='S$', decimals=2)
        sgd = self.mgr.get('SGD')
        assert sgd is not None
        assert sgd['symbol'] == 'S$'

    def test_deactivate_currency(self):
        self.mgr.deactivate('JPY')
        jpy = self.mgr.get('JPY')
        assert jpy['active'] is False

    def test_list_active_only(self):
        self.mgr.deactivate('CNY')
        active = self.mgr.list_all(active_only=True)
        codes = [c['code'] for c in active]
        assert 'CNY' not in codes


class TestCurrencyConverter:
    def setup_method(self):
        from src.multicurrency.conversion import CurrencyConverter
        self.converter = CurrencyConverter()

    def test_convert_krw_to_usd(self):
        result = self.converter.convert(13500, 'KRW', 'USD')
        assert result == pytest.approx(10.0, rel=0.01)

    def test_convert_same_currency(self):
        assert self.converter.convert(1000, 'KRW', 'KRW') == 1000.0

    def test_convert_usd_to_eur(self):
        result = self.converter.convert(100, 'USD', 'EUR')
        assert isinstance(result, float)
        assert result > 0

    def test_invalid_currency(self):
        with pytest.raises(ValueError):
            self.converter.convert(100, 'XYZ', 'KRW')

    def test_get_rate(self):
        rate = self.converter.get_rate('USD', 'KRW')
        assert rate == pytest.approx(1350, rel=0.1)

    def test_cache_valid(self):
        assert self.converter.is_cache_valid()

    def test_update_rates(self):
        self.converter.update_rates({'USD': 1400.0})
        rate = self.converter.get_rate('USD', 'KRW')
        assert rate == pytest.approx(1400, rel=0.01)


class TestCurrencyDisplay:
    def setup_method(self):
        from src.multicurrency.display import CurrencyDisplay
        self.display = CurrencyDisplay()

    def test_format_krw(self):
        result = self.display.format(12300, 'KRW')
        assert result == '₩12,300'

    def test_format_usd(self):
        result = self.display.format(12.30, 'USD')
        assert result == '$12.30'

    def test_format_jpy(self):
        result = self.display.format(1230, 'JPY')
        assert result == '¥1,230'

    def test_parse_krw(self):
        result = self.display.parse('₩12,300', 'KRW')
        assert result == pytest.approx(12300.0)

    def test_parse_usd(self):
        result = self.display.parse('$12.30', 'USD')
        assert result == pytest.approx(12.30)


class TestSettlementCalculator:
    def setup_method(self):
        from src.multicurrency.settlement import SettlementCalculator
        self.calc = SettlementCalculator()

    def test_krw_no_fee(self):
        result = self.calc.calculate(100000, 'KRW')
        assert result['fee_amount_krw'] == 0.0
        assert result['net_amount_krw'] == 100000.0

    def test_usd_with_fee(self):
        result = self.calc.calculate(100000, 'USD')
        assert result['fee_pct'] == 1.5
        assert result['fee_amount_krw'] > 0

    def test_min_fee_applied(self):
        # Small amount — min fee should kick in
        result = self.calc.calculate(100, 'USD')
        assert result['fee_amount_krw'] >= 500
