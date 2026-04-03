"""tests/test_tax_engine.py — Phase 90: 세금 계산 엔진 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.tax_engine import (
    TaxRate,
    TaxCalculator,
    TaxRule,
    VATRule,
    CustomsDutyRule,
    ExciseTaxRule,
    TaxExemption,
    TaxBracket,
    CrossBorderTax,
    TaxReport,
    TaxInvoice,
)


class TestTaxRate:
    def test_dataclass_fields(self):
        rate = TaxRate(
            country='KR',
            region='Seoul',
            category='general',
            rate=0.10,
            name='부가가치세',
            is_inclusive=False,
        )
        assert rate.country == 'KR'
        assert rate.rate == 0.10
        assert not rate.is_inclusive


class TestVATRule:
    def test_calculate_default(self):
        vat = VATRule()
        result = vat.calculate(100000, {})
        assert result['tax'] == 10000.0
        assert result['rate'] == 0.10
        assert result['rule'] == 'VAT'

    def test_calculate_custom_rate(self):
        vat = VATRule()
        result = vat.calculate(100000, {'vat_rate': 0.05})
        assert result['tax'] == 5000.0

    def test_rule_name(self):
        vat = VATRule()
        assert vat.rule_name() == 'VAT'


class TestCustomsDutyRule:
    def test_calculate_us(self):
        customs = CustomsDutyRule()
        result = customs.calculate(100000, {'origin_country': 'US'})
        assert result['rule'] == 'customs_duty'
        assert result['rate'] == 0.08
        assert result['tax'] == 8000.0

    def test_calculate_japan(self):
        customs = CustomsDutyRule()
        result = customs.calculate(100000, {'origin_country': 'JP'})
        assert result['rate'] == 0.05
        assert result['tax'] == 5000.0

    def test_calculate_china(self):
        customs = CustomsDutyRule()
        result = customs.calculate(100000, {'origin_country': 'CN'})
        assert result['rate'] == 0.15

    def test_calculate_default_origin(self):
        customs = CustomsDutyRule()
        result = customs.calculate(100000, {})
        assert result['rate'] == 0.08  # US default

    def test_rule_name(self):
        customs = CustomsDutyRule()
        assert customs.rule_name() == 'customs_duty'


class TestExciseTaxRule:
    def test_calculate(self):
        excise = ExciseTaxRule()
        result = excise.calculate(100000, {})
        assert result['rule'] == 'excise_tax'
        assert result['rate'] == 0.05
        assert result['tax'] == 5000.0

    def test_calculate_custom_rate(self):
        excise = ExciseTaxRule()
        result = excise.calculate(100000, {'excise_rate': 0.10})
        assert result['tax'] == 10000.0

    def test_rule_name(self):
        excise = ExciseTaxRule()
        assert excise.rule_name() == 'excise_tax'


class TestTaxCalculator:
    def test_default_vat(self):
        calc = TaxCalculator()
        result = calc.calculate(100000)
        assert result['total_tax'] == 10000.0
        assert result['tax_inclusive_amount'] == 110000.0
        assert len(result['breakdown']) == 1

    def test_multiple_rules(self):
        calc = TaxCalculator()
        calc.add_rule(ExciseTaxRule())
        result = calc.calculate(100000)
        assert result['total_tax'] == 15000.0  # 10% VAT + 5% excise
        assert len(result['breakdown']) == 2

    def test_calculate_with_context(self):
        calc = TaxCalculator()
        result = calc.calculate(100000, context={'vat_rate': 0.05})
        assert result['total_tax'] == 5000.0


class TestTaxExemption:
    def test_de_minimis(self):
        exemption = TaxExemption()
        assert exemption.is_exempt(100000)  # <= 150000 default
        assert not exemption.is_exempt(200000)

    def test_category_exempt(self):
        exemption = TaxExemption()
        exemption.add_exempt_category('의약품')
        assert exemption.is_exempt(999999, '의약품')  # any amount for exempt category

    def test_set_de_minimis(self):
        exemption = TaxExemption()
        exemption.set_de_minimis(50000)
        assert exemption.is_exempt(40000)
        assert not exemption.is_exempt(60000)


class TestTaxBracket:
    def test_empty_brackets(self):
        bracket = TaxBracket()
        assert bracket.get_rate(100000) == 0.0

    def test_brackets(self):
        bracket = TaxBracket()
        bracket.add_bracket(100000, 0.05)
        bracket.add_bracket(500000, 0.10)
        bracket.add_bracket(1000000, 0.15)
        assert bracket.get_rate(50000) == 0.05
        assert bracket.get_rate(200000) == 0.10
        assert bracket.get_rate(999999) == 0.15
        assert bracket.get_rate(1500000) == 0.15  # above highest bracket

    def test_calculate(self):
        bracket = TaxBracket()
        bracket.add_bracket(1000000, 0.10)
        result = bracket.calculate(500000)
        assert result['rate'] == 0.10
        assert result['tax'] == 50000.0


class TestCrossBorderTax:
    def test_exempt_amount(self):
        cb = CrossBorderTax()
        result = cb.calculate(100000)  # <= 150000, exempt
        assert result['exempt']
        assert result['total_tax'] == 0

    def test_taxable_amount(self):
        cb = CrossBorderTax()
        result = cb.calculate(200000, origin_country='US')
        assert not result['exempt']
        assert result['total_tax'] > 0
        assert len(result['breakdown']) >= 2

    def test_with_excise(self):
        cb = CrossBorderTax()
        result = cb.calculate(200000, origin_country='US', apply_excise=True)
        assert len(result['breakdown']) == 3

    def test_without_excise(self):
        cb = CrossBorderTax()
        result = cb.calculate(200000, origin_country='JP', apply_excise=False)
        assert len(result['breakdown']) == 2

    def test_category_exempt(self):
        cb = CrossBorderTax()
        # Override exemption - medicine category always exempt
        result = cb.calculate(500000, category='의약품')
        # Default exemption doesn't include this, but should still check amount
        # 500000 > 150000 so not exempt by de minimis
        assert not result['exempt']  # no category exemption added


class TestTaxReport:
    def test_record_and_summary(self):
        report = TaxReport()
        report.record(100000, 10000, category='전자기기', timestamp='2024-01-15T10:00:00')
        report.record(200000, 20000, category='의류', timestamp='2024-01-20T10:00:00')
        summary = report.period_summary('2024-01-01', '2024-01-31')
        assert summary['count'] == 2
        assert summary['total_tax'] == 30000.0

    def test_period_filter(self):
        report = TaxReport()
        report.record(100000, 10000, timestamp='2024-01-15T10:00:00')
        report.record(200000, 20000, timestamp='2024-02-15T10:00:00')
        summary = report.period_summary('2024-01-01', '2024-01-31')
        assert summary['count'] == 1

    def test_by_category(self):
        report = TaxReport()
        report.record(100000, 10000, category='전자기기')
        report.record(50000, 5000, category='전자기기')
        report.record(200000, 20000, category='의류')
        by_cat = report.by_category()
        assert by_cat['전자기기'] == 15000.0
        assert by_cat['의류'] == 20000.0


class TestTaxInvoice:
    def test_create(self):
        invoice = TaxInvoice()
        supplier = {'name': '공급자', 'registration_number': '123-45-67890'}
        buyer = {'name': '구매자', 'registration_number': '987-65-43210'}
        items = [
            {'description': '상품A', 'amount': 100000, 'tax': 10000},
            {'description': '상품B', 'amount': 200000, 'tax': 20000},
        ]
        result = invoice.create(supplier, buyer, items)
        assert result['invoice_id']
        assert result['subtotal'] == 300000
        assert result['total_tax'] == 30000.0
        assert result['total'] == 330000.0
        assert result['issue_date']

    def test_create_empty_items(self):
        invoice = TaxInvoice()
        result = invoice.create({}, {}, [])
        assert result['subtotal'] == 0
        assert result['total_tax'] == 0.0
        assert result['total'] == 0.0
