"""src/shipping 패키지 단위 테스트 (60개+).

커버리지:
- CountryConfig / get_country(): 13개국 설정 검증
- TaxCalculator.calc_import_tax(): 13개국 × 면세/과세 케이스
- TaxCalculator.calc_landed_price(): 마진, DDP/DAP, 다양한 통화
- ShippingEstimator: 모든 zone × method, cheapest/fastest
- CustomsDocumentHelper: 인보이스 생성, HS 코드 매핑
- 엣지 케이스: 미지원 국가, 0원 상품, 음수 마진, 환율 없음
"""
import sys
import os
from decimal import Decimal
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.shipping.country_config import (  # noqa: E402
    COUNTRY_DB,
    SUPPORTED_COUNTRIES,
    get_country,
)
from src.shipping.tax_calculator import TaxCalculator, _convert_currency  # noqa: E402
from src.shipping.shipping_estimator import ShippingEstimate, ShippingEstimator  # noqa: E402
from src.shipping.customs_document import CustomsDocumentHelper, HS_CODE_MAP  # noqa: E402

# ── 테스트용 고정 환율 (모든 지원 통화) ───────────────────────────────────────
FX = {
    'USDKRW': Decimal('1350'),
    'JPYKRW': Decimal('9.0'),
    'EURKRW': Decimal('1470'),
    'GBPKRW': Decimal('1710'),
    'THBKRW': Decimal('38'),
    'VNDKRW': Decimal('0.055'),
    'IDRKRW': Decimal('0.087'),
    'PHPKRW': Decimal('23'),
    'AEDKRW': Decimal('367'),
    'SARKRW': Decimal('360'),
    'SGDKRW': Decimal('1000'),
    'MYRKRW': Decimal('290'),
    'PLNKRW': Decimal('330'),
    'CNYKRW': Decimal('186'),
}

calc = TaxCalculator()
estimator = ShippingEstimator()
doc_helper = CustomsDocumentHelper()


# ══════════════════════════════════════════════════════════════════════════════
# 1. CountryConfig / get_country() 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestSupportedCountries:
    def test_count_is_13(self):
        assert len(SUPPORTED_COUNTRIES) == 13

    def test_all_expected_codes_present(self):
        expected = {'US', 'GB', 'JP', 'TH', 'VN', 'ID', 'PH', 'AE', 'SA', 'SG', 'MY', 'PL', 'CN'}
        assert set(SUPPORTED_COUNTRIES) == expected

    def test_country_db_keys_match(self):
        assert set(COUNTRY_DB.keys()) == set(SUPPORTED_COUNTRIES)


class TestGetCountry:
    def test_us_basic(self):
        c = get_country('US')
        assert c.code == 'US'
        assert c.currency == 'USD'
        assert c.vat_rate == Decimal('0')
        assert c.duty_rate == Decimal('0.05')
        assert c.de_minimis == Decimal('800')
        assert c.incoterms == 'DAP'
        assert c.tier == 1

    def test_gb_basic(self):
        c = get_country('GB')
        assert c.currency == 'GBP'
        assert c.vat_rate == Decimal('0.20')
        assert c.duty_rate == Decimal('0.04')
        assert c.de_minimis == Decimal('135')
        assert c.incoterms == 'DDP'
        assert c.tier == 1

    def test_jp_basic(self):
        c = get_country('JP')
        assert c.currency == 'JPY'
        assert c.vat_rate == Decimal('0.10')
        assert c.de_minimis == Decimal('10000')
        assert c.tier == 2

    def test_th_no_de_minimis(self):
        c = get_country('TH')
        assert c.de_minimis == Decimal('0')
        assert c.vat_rate == Decimal('0.07')
        assert c.duty_rate == Decimal('0.10')

    def test_vn_no_de_minimis(self):
        c = get_country('VN')
        assert c.de_minimis == Decimal('0')
        assert c.vat_rate == Decimal('0.10')

    def test_id_usd_de_minimis(self):
        c = get_country('ID')
        assert c.de_minimis == Decimal('3')
        assert c.de_minimis_currency == 'USD'
        assert c.vat_rate == Decimal('0.11')

    def test_ph_basic(self):
        c = get_country('PH')
        assert c.de_minimis == Decimal('10000')
        assert c.de_minimis_currency == 'PHP'
        assert c.vat_rate == Decimal('0.12')

    def test_ae_basic(self):
        c = get_country('AE')
        assert c.vat_rate == Decimal('0.05')
        assert c.duty_rate == Decimal('0.05')
        assert c.de_minimis == Decimal('0')

    def test_sa_basic(self):
        c = get_country('SA')
        assert c.vat_rate == Decimal('0.15')
        assert c.de_minimis == Decimal('0')

    def test_sg_no_duty(self):
        c = get_country('SG')
        assert c.duty_rate == Decimal('0')
        assert c.vat_rate == Decimal('0.09')
        assert c.de_minimis == Decimal('400')

    def test_my_basic(self):
        c = get_country('MY')
        assert c.vat_rate == Decimal('0.10')
        assert c.de_minimis == Decimal('500')

    def test_pl_ioss(self):
        c = get_country('PL')
        assert c.ioss_eligible is True
        assert c.ioss_threshold == Decimal('150')
        assert c.vat_rate == Decimal('0.23')
        assert c.incoterms == 'DDP'

    def test_cn_basic(self):
        c = get_country('CN')
        assert c.de_minimis == Decimal('50')
        assert c.de_minimis_currency == 'CNY'
        assert c.vat_rate == Decimal('0.13')

    def test_case_insensitive_lookup(self):
        assert get_country('us').code == 'US'
        assert get_country('gb').code == 'GB'
        assert get_country(' JP ').code == 'JP'

    def test_unknown_country_raises(self):
        with pytest.raises(ValueError, match='지원하지 않는 국가'):
            get_country('KR')

    def test_unknown_country_raises_with_code(self):
        with pytest.raises(ValueError, match='ZZ'):
            get_country('ZZ')


class TestCountryConfigImmutable:
    def test_frozen_dataclass(self):
        c = get_country('US')
        with pytest.raises((AttributeError, TypeError)):
            c.vat_rate = Decimal('0.1')  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════════════════
# 2. _convert_currency 헬퍼 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestConvertCurrency:
    def test_same_currency(self):
        assert _convert_currency(Decimal('100'), 'USD', 'USD', FX) == Decimal('100')

    def test_usd_to_krw(self):
        result = _convert_currency(Decimal('100'), 'USD', 'KRW', FX)
        assert result == Decimal('135000')

    def test_krw_to_usd(self):
        result = _convert_currency(Decimal('135000'), 'KRW', 'USD', FX)
        assert result == Decimal('100')

    def test_usd_to_gbp(self):
        # 100 USD → 135000 KRW → / 1710 GBP ≈ 78.947...
        result = _convert_currency(Decimal('100'), 'USD', 'GBP', FX)
        expected = Decimal('135000') / Decimal('1710')
        assert result == expected

    def test_missing_rate_raises(self):
        with pytest.raises(ValueError, match='환율 정보 없음'):
            _convert_currency(Decimal('100'), 'USD', 'BTC', FX)


# ══════════════════════════════════════════════════════════════════════════════
# 3. TaxCalculator.calc_import_tax() 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestTaxCalcUS:
    """미국: 연방 VAT 없음, $800 de minimis"""

    def test_below_de_minimis_fully_exempt(self):
        # $500 < $800: fully exempt (duty=0, vat=0 because vat_rate=0)
        r = calc.calc_import_tax('US', Decimal('500'), 'USD', fx_rates=FX)
        assert r['de_minimis_exempt'] is True
        assert r['duty'] == Decimal('0')
        assert r['vat'] == Decimal('0')
        assert r['total_tax'] == Decimal('0')

    def test_exactly_de_minimis_exempt(self):
        r = calc.calc_import_tax('US', Decimal('800'), 'USD', fx_rates=FX)
        assert r['de_minimis_exempt'] is True

    def test_above_de_minimis_duty_applies(self):
        # $1000 > $800: duty 5%, no VAT
        r = calc.calc_import_tax('US', Decimal('1000'), 'USD', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        # CIF = 1000 + 0 = 1000 USD → 1350000 KRW... but wait,
        # goods_value is in USD, result is in USD (country currency)
        assert r['goods_value_local'] == Decimal('1000')
        assert r['duty'] == Decimal('1000') * Decimal('0.05')
        assert r['vat'] == Decimal('0')

    def test_return_structure(self):
        r = calc.calc_import_tax('US', Decimal('100'), 'USD', fx_rates=FX)
        for key in ('country', 'goods_value_local', 'shipping_cost_local',
                    'de_minimis_exempt', 'duty', 'vat', 'total_tax',
                    'total_landed', 'incoterms', 'notes', 'breakdown'):
            assert key in r


class TestTaxCalcGB:
    """영국: VAT 20%, £135 이하 관세 면제 + VAT 부과"""

    def test_below_135_duty_exempt_vat_applies(self):
        # £100 < £135: 관세 0, VAT 20%
        r = calc.calc_import_tax('GB', Decimal('100'), 'GBP', fx_rates=FX)
        assert r['de_minimis_exempt'] is True
        assert r['duty'] == Decimal('0')
        assert r['vat'] == Decimal('100') * Decimal('0.20')

    def test_above_135_both_apply(self):
        # £200 > £135: 관세 4% + VAT 20%
        r = calc.calc_import_tax('GB', Decimal('200'), 'GBP', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        duty = Decimal('200') * Decimal('0.04')
        assert r['duty'] == duty
        vat_base = Decimal('200') + duty  # vat_on_shipping=True but shipping=0
        assert r['vat'] == vat_base * Decimal('0.20')

    def test_usd_goods_to_gbp(self):
        # $200 USD → GBP 환산 후 de_minimis 판정
        r = calc.calc_import_tax('GB', Decimal('200'), 'USD', fx_rates=FX)
        # $200 * 1350 / 1710 ≈ 157.89 GBP > 135 → 과세
        assert r['de_minimis_exempt'] is False


class TestTaxCalcJP:
    """일본: ¥10,000 이하 완전 면세"""

    def test_below_10000_fully_exempt(self):
        r = calc.calc_import_tax('JP', Decimal('5000'), 'JPY', fx_rates=FX)
        assert r['de_minimis_exempt'] is True
        assert r['duty'] == Decimal('0')
        assert r['vat'] == Decimal('0')

    def test_above_10000_duty_and_vat(self):
        r = calc.calc_import_tax('JP', Decimal('15000'), 'JPY', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        duty = Decimal('15000') * Decimal('0.05')
        assert r['duty'] == duty
        vat_base = Decimal('15000') + duty  # vat_on_shipping=True, shipping=0
        assert r['vat'] == vat_base * Decimal('0.10')


class TestTaxCalcTH:
    """태국: de_minimis=0, 항상 관세+VAT"""

    def test_always_taxed(self):
        r = calc.calc_import_tax('TH', Decimal('100'), 'USD', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        assert r['duty'] > Decimal('0')
        assert r['vat'] > Decimal('0')

    def test_vat_rate_7pct(self):
        r = calc.calc_import_tax('TH', Decimal('1000'), 'THB', fx_rates=FX)
        duty = Decimal('1000') * Decimal('0.10')
        vat_base = Decimal('1000') + duty
        assert r['vat'] == vat_base * Decimal('0.07')


class TestTaxCalcVN:
    """베트남: de_minimis=0, 항상 관세+VAT"""

    def test_always_taxed(self):
        r = calc.calc_import_tax('VN', Decimal('500000'), 'VND', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        duty = Decimal('500000') * Decimal('0.10')
        vat_base = Decimal('500000') + duty
        assert r['vat'] == vat_base * Decimal('0.10')


class TestTaxCalcID:
    """인도네시아: $3 이하 관세 면제 + VAT 11%"""

    def test_below_3usd_duty_exempt_vat_applies(self):
        # $2 ≤ $3: 관세 0, VAT 11%
        r = calc.calc_import_tax('ID', Decimal('2'), 'USD', fx_rates=FX)
        assert r['de_minimis_exempt'] is True
        assert r['duty'] == Decimal('0')
        assert r['vat'] > Decimal('0')  # VAT still applies

    def test_above_3usd_both_apply(self):
        r = calc.calc_import_tax('ID', Decimal('10'), 'USD', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        assert r['duty'] > Decimal('0')
        assert r['vat'] > Decimal('0')


class TestTaxCalcPH:
    """필리핀: ₱10,000 이하 완전 면세"""

    def test_below_10000php_fully_exempt(self):
        r = calc.calc_import_tax('PH', Decimal('5000'), 'PHP', fx_rates=FX)
        assert r['de_minimis_exempt'] is True
        assert r['duty'] == Decimal('0')
        assert r['vat'] == Decimal('0')

    def test_above_10000php_taxed(self):
        r = calc.calc_import_tax('PH', Decimal('15000'), 'PHP', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        assert r['duty'] > Decimal('0')
        assert r['vat'] > Decimal('0')


class TestTaxCalcAE:
    """UAE: de_minimis=0, 관세 5% + VAT 5%"""

    def test_always_taxed(self):
        r = calc.calc_import_tax('AE', Decimal('100'), 'USD', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        aed_val = _convert_currency(Decimal('100'), 'USD', 'AED', FX)
        duty = aed_val * Decimal('0.05')
        assert r['duty'] == duty

    def test_vat_5pct(self):
        r = calc.calc_import_tax('AE', Decimal('1000'), 'AED', fx_rates=FX)
        duty = Decimal('1000') * Decimal('0.05')
        vat_base = Decimal('1000') + duty
        assert r['vat'] == vat_base * Decimal('0.05')


class TestTaxCalcSA:
    """사우디: de_minimis=0, 관세 5% + VAT 15%"""

    def test_always_taxed(self):
        r = calc.calc_import_tax('SA', Decimal('500'), 'SAR', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        duty = Decimal('500') * Decimal('0.05')
        vat_base = Decimal('500') + duty
        assert r['vat'] == vat_base * Decimal('0.15')


class TestTaxCalcSG:
    """싱가포르: S$400 이하 VAT 면제 (duty_rate=0)"""

    def test_below_400sgd_exempt(self):
        r = calc.calc_import_tax('SG', Decimal('200'), 'SGD', fx_rates=FX)
        assert r['de_minimis_exempt'] is True
        assert r['duty'] == Decimal('0')

    def test_above_400sgd_vat_applies(self):
        r = calc.calc_import_tax('SG', Decimal('500'), 'SGD', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        # duty_rate=0, vat_rate=9%
        assert r['duty'] == Decimal('0')
        vat_base = Decimal('500')
        assert r['vat'] == vat_base * Decimal('0.09')


class TestTaxCalcMY:
    """말레이시아: RM500 이하 VAT 10% 부과 (duty_rate=5%)"""

    def test_below_500myr_vat_applies(self):
        # MYR ≤ 500: de_minimis_exempt, but MY is NOT in full_exemption_countries
        r = calc.calc_import_tax('MY', Decimal('300'), 'MYR', fx_rates=FX)
        assert r['de_minimis_exempt'] is True
        assert r['duty'] == Decimal('0')
        assert r['vat'] == Decimal('300') * Decimal('0.10')

    def test_above_500myr_full_tax(self):
        r = calc.calc_import_tax('MY', Decimal('600'), 'MYR', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        duty = Decimal('600') * Decimal('0.05')
        assert r['duty'] == duty


class TestTaxCalcPL:
    """폴란드(EU IOSS): de_minimis=0, VAT 23%"""

    def test_always_taxed(self):
        r = calc.calc_import_tax('PL', Decimal('100'), 'EUR', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        assert r['breakdown']['ioss_eligible'] is True

    def test_vat_23pct(self):
        pln_val = _convert_currency(Decimal('100'), 'EUR', 'PLN', FX)
        r = calc.calc_import_tax('PL', Decimal('100'), 'EUR', fx_rates=FX)
        duty = pln_val * Decimal('0.04')
        vat_base = pln_val + duty
        assert r['vat'] == vat_base * Decimal('0.23')


class TestTaxCalcCN:
    """중국: ¥50 이하 면세 (개인우편물 기준)"""

    def test_below_50cny_exempt(self):
        r = calc.calc_import_tax('CN', Decimal('30'), 'CNY', fx_rates=FX)
        assert r['de_minimis_exempt'] is True

    def test_above_50cny_taxed(self):
        r = calc.calc_import_tax('CN', Decimal('100'), 'CNY', fx_rates=FX)
        assert r['de_minimis_exempt'] is False
        duty = Decimal('100') * Decimal('0.10')
        assert r['duty'] == duty


# ══════════════════════════════════════════════════════════════════════════════
# 4. TaxCalculator 공통 동작 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestTaxCalcShipping:
    """배송비 포함 계산 테스트"""

    def test_shipping_included_in_cif(self):
        # GB £200 + shipping £20: duty on CIF = (200+20)*4%
        r = calc.calc_import_tax('GB', Decimal('200'), 'GBP',
                                 shipping_cost=Decimal('20'), fx_rates=FX)
        duty = Decimal('220') * Decimal('0.04')
        assert r['duty'] == duty

    def test_us_no_vat_on_shipping(self):
        # US: vat_on_shipping=False, vat_rate=0 anyway
        r = calc.calc_import_tax('US', Decimal('1000'), 'USD',
                                 shipping_cost=Decimal('50'), fx_rates=FX)
        assert r['vat'] == Decimal('0')

    def test_total_landed_includes_shipping(self):
        r = calc.calc_import_tax('AE', Decimal('100'), 'AED',
                                 shipping_cost=Decimal('10'), fx_rates=FX)
        assert r['total_landed'] == r['goods_value_local'] + r['shipping_cost_local'] + r['total_tax']


class TestTaxCalcZeroGoods:
    """상품가 0원 엣지 케이스"""

    def test_zero_value_no_tax(self):
        r = calc.calc_import_tax('US', Decimal('0'), 'USD', fx_rates=FX)
        assert r['duty'] == Decimal('0')
        assert r['vat'] == Decimal('0')
        assert r['total_tax'] == Decimal('0')


class TestTaxCalcUnsupportedCountry:
    def test_invalid_country_raises(self):
        with pytest.raises(ValueError, match='지원하지 않는 국가'):
            calc.calc_import_tax('KR', Decimal('100'), 'KRW', fx_rates=FX)

    def test_missing_fx_rate_raises(self):
        with pytest.raises(ValueError, match='환율 정보 없음'):
            calc.calc_import_tax('GB', Decimal('100'), 'USD', fx_rates={})


# ══════════════════════════════════════════════════════════════════════════════
# 5. TaxCalculator.calc_landed_price() 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestCalcLandedPrice:
    def test_return_structure(self):
        r = calc.calc_landed_price('US', Decimal('100'), 'USD',
                                   margin_pct=Decimal('30'), fx_rates=FX)
        for key in ('sell_price', 'tax_inclusive_price', 'tax_detail',
                    'margin_amount', 'fx_rate_used'):
            assert key in r

    def test_sell_price_greater_than_tax_inclusive(self):
        r = calc.calc_landed_price('US', Decimal('100'), 'USD',
                                   margin_pct=Decimal('20'), fx_rates=FX)
        assert r['sell_price'] > r['tax_inclusive_price']

    def test_zero_margin(self):
        r = calc.calc_landed_price('US', Decimal('100'), 'USD',
                                   margin_pct=Decimal('0'), fx_rates=FX)
        assert r['sell_price'] == r['tax_inclusive_price']
        assert r['margin_amount'] == Decimal('0')

    def test_negative_margin_reduces_price(self):
        r = calc.calc_landed_price('US', Decimal('100'), 'USD',
                                   margin_pct=Decimal('-10'), fx_rates=FX)
        assert r['sell_price'] < r['tax_inclusive_price']

    def test_target_currency_override(self):
        # Buy in USD, sell in JPY
        r = calc.calc_landed_price('JP', Decimal('100'), 'USD',
                                   margin_pct=Decimal('20'),
                                   target_currency='JPY', fx_rates=FX)
        assert r['tax_detail']['country'] == 'JP'
        # sell_price should be in JPY (large number)
        assert r['sell_price'] > Decimal('1000')

    def test_gb_ddp_with_margin(self):
        # Buy £50 < £135 de_minimis → no duty, VAT 20%
        r = calc.calc_landed_price('GB', Decimal('50'), 'GBP',
                                   margin_pct=Decimal('25'), fx_rates=FX)
        vat = Decimal('50') * Decimal('0.20')
        tax_inclusive = Decimal('50') + vat
        assert r['tax_inclusive_price'] == tax_inclusive
        assert r['sell_price'] == round(tax_inclusive * Decimal('1.25'), 2)

    def test_margin_amount_correct(self):
        r = calc.calc_landed_price('US', Decimal('800'), 'USD',
                                   margin_pct=Decimal('10'), fx_rates=FX)
        assert r['margin_amount'] == round(r['sell_price'] - r['tax_inclusive_price'], 2)


# ══════════════════════════════════════════════════════════════════════════════
# 6. ShippingEstimator 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestShippingEstimatorZones:
    def test_jp_in_asia_near(self):
        estimates = estimator.estimate('JP')
        assert len(estimates) == 3
        costs = {e.method: e.cost_krw for e in estimates}
        assert costs['EMS'] == Decimal('18000')
        assert costs['K-Packet'] == Decimal('8000')

    def test_th_in_asia_far(self):
        estimates = estimator.estimate('TH')
        costs = {e.method: e.cost_krw for e in estimates}
        assert costs['EMS'] == Decimal('22000')

    def test_us_in_americas(self):
        estimates = estimator.estimate('US')
        costs = {e.method: e.cost_krw for e in estimates}
        assert costs['EMS'] == Decimal('28000')

    def test_gb_in_europe(self):
        estimates = estimator.estimate('GB')
        costs = {e.method: e.cost_krw for e in estimates}
        assert costs['K-Packet'] == Decimal('13000')

    def test_ae_in_middle_east(self):
        estimates = estimator.estimate('AE')
        costs = {e.method: e.cost_krw for e in estimates}
        assert costs['EMS'] == Decimal('25000')

    def test_sa_in_middle_east(self):
        estimates = estimator.estimate('SA')
        costs = {e.method: e.cost_krw for e in estimates}
        assert costs['EMS'] == Decimal('25000')


class TestShippingEstimatorMethods:
    def test_single_method_filter(self):
        estimates = estimator.estimate('JP', method='ems')
        assert len(estimates) == 1
        assert estimates[0].method == 'EMS'

    def test_k_packet_method(self):
        estimates = estimator.estimate('US', method='k_packet')
        assert len(estimates) == 1
        assert estimates[0].method == 'K-Packet'

    def test_registered_method(self):
        estimates = estimator.estimate('GB', method='registered')
        assert len(estimates) == 1
        assert estimates[0].method == 'registered_mail'

    def test_all_methods_have_tracking(self):
        for e in estimator.estimate('JP'):
            assert e.tracking is True

    def test_sorted_by_cost(self):
        estimates = estimator.estimate('JP')
        costs = [e.cost_krw for e in estimates]
        assert costs == sorted(costs)


class TestShippingEstimatorWeightScaling:
    def test_base_weight_0_5kg(self):
        e = estimator.estimate('JP', weight_kg=Decimal('0.5'))
        ems = next(x for x in e if x.method == 'EMS')
        assert ems.cost_krw == Decimal('18000')

    def test_weight_1kg_doubles_cost(self):
        e = estimator.estimate('JP', weight_kg=Decimal('1.0'))
        ems = next(x for x in e if x.method == 'EMS')
        assert ems.cost_krw == Decimal('36000')  # 18000 * 2

    def test_weight_0_3kg_rounds_up(self):
        # 0.3kg → ceil(0.3/0.5)=1 → base rate
        e = estimator.estimate('JP', weight_kg=Decimal('0.3'))
        ems = next(x for x in e if x.method == 'EMS')
        assert ems.cost_krw == Decimal('18000')

    def test_weight_0_6kg_rounds_to_2(self):
        # 0.6kg → ceil(0.6/0.5)=2 → 2× base
        e = estimator.estimate('JP', weight_kg=Decimal('0.6'))
        ems = next(x for x in e if x.method == 'EMS')
        assert ems.cost_krw == Decimal('36000')


class TestShippingEstimatorDeliveryDays:
    def test_asia_near_ems_days(self):
        estimates = estimator.estimate('JP')
        ems = next(x for x in estimates if x.method == 'EMS')
        assert ems.delivery_days_min == 2
        assert ems.delivery_days_max == 4

    def test_americas_k_packet_days(self):
        estimates = estimator.estimate('US')
        kp = next(x for x in estimates if x.method == 'K-Packet')
        assert kp.delivery_days_min == 10
        assert kp.delivery_days_max == 18


class TestShippingEstimatorCheapestFastest:
    def test_cheapest_returns_single(self):
        e = estimator.cheapest('JP')
        assert isinstance(e, ShippingEstimate)

    def test_cheapest_is_registered(self):
        e = estimator.cheapest('JP')
        assert e.method == 'registered_mail'

    def test_fastest_is_ems(self):
        e = estimator.fastest('JP')
        assert e.method == 'EMS'

    def test_cheapest_us(self):
        e = estimator.cheapest('US')
        assert e.method == 'registered_mail'
        assert e.cost_krw == Decimal('8000')

    def test_unsupported_country_raises(self):
        with pytest.raises(ValueError, match='지원하지 않는 국가'):
            estimator.estimate('KR')


# ══════════════════════════════════════════════════════════════════════════════
# 7. CustomsDocumentHelper 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestHsCodeMapping:
    def test_bag_hs_code(self):
        assert doc_helper.get_hs_code('bag') == '4202.21'

    def test_wallet_hs_code(self):
        assert doc_helper.get_hs_code('wallet') == '4202.31'

    def test_perfume_hs_code(self):
        assert doc_helper.get_hs_code('perfume') == '3303.00'

    def test_cosmetics_hs_code(self):
        assert doc_helper.get_hs_code('cosmetics') == '3304.99'

    def test_clothing_hs_code(self):
        assert doc_helper.get_hs_code('clothing') == '6109.10'

    def test_accessories_hs_code(self):
        assert doc_helper.get_hs_code('accessories') == '7117.19'

    def test_unknown_category_fallback(self):
        assert doc_helper.get_hs_code('unknown_item') == '9999.99'

    def test_case_insensitive(self):
        assert doc_helper.get_hs_code('BAG') == '4202.21'
        assert doc_helper.get_hs_code('Perfume') == '3303.00'

    def test_all_hs_map_keys_covered(self):
        for cat in HS_CODE_MAP:
            assert doc_helper.get_hs_code(cat) == HS_CODE_MAP[cat]


class TestGenerateInvoiceData:
    _sender = {'name': 'Proxy Commerce', 'address': 'Seoul, KR', 'phone': '+82-10-1234-5678'}
    _receiver = {'name': 'John Doe', 'address': 'London, GB', 'phone': '+44-7911-123456'}
    _items = [
        {
            'description': 'Leather Bag',
            'category': 'bag',
            'quantity': 1,
            'unit_value': Decimal('120'),
            'currency': 'GBP',
            'origin_country': 'KR',
            'weight_kg': Decimal('0.5'),
        }
    ]

    def test_invoice_has_required_keys(self):
        inv = doc_helper.generate_invoice_data(
            self._items, 'GB', self._sender, self._receiver
        )
        for key in ('invoice_number', 'date', 'sender', 'receiver',
                    'items', 'total_value', 'currency', 'incoterms'):
            assert key in inv

    def test_invoice_number_format(self):
        inv = doc_helper.generate_invoice_data(
            self._items, 'GB', self._sender, self._receiver
        )
        assert inv['invoice_number'].startswith('INV-')

    def test_total_value_correct(self):
        inv = doc_helper.generate_invoice_data(
            self._items, 'GB', self._sender, self._receiver
        )
        assert inv['total_value'] == Decimal('120')

    def test_incoterms_from_country(self):
        inv = doc_helper.generate_invoice_data(
            self._items, 'GB', self._sender, self._receiver
        )
        assert inv['incoterms'] == 'DDP'  # GB uses DDP

    def test_hs_code_auto_mapped(self):
        inv = doc_helper.generate_invoice_data(
            self._items, 'GB', self._sender, self._receiver
        )
        assert inv['items'][0]['hs_code'] == '4202.21'

    def test_hs_code_explicit_override(self):
        items = [{**self._items[0], 'hs_code': '4202.99'}]
        inv = doc_helper.generate_invoice_data(items, 'GB', self._sender, self._receiver)
        assert inv['items'][0]['hs_code'] == '4202.99'

    def test_multi_item_total(self):
        items = [
            {**self._items[0], 'quantity': 2, 'unit_value': Decimal('50')},
            {**self._items[0], 'category': 'wallet', 'quantity': 1, 'unit_value': Decimal('30')},
        ]
        inv = doc_helper.generate_invoice_data(items, 'US', self._sender, self._receiver)
        assert inv['total_value'] == Decimal('130')  # 2*50 + 1*30

    def test_dap_country_incoterms(self):
        inv = doc_helper.generate_invoice_data(
            self._items, 'US', self._sender, self._receiver
        )
        assert inv['incoterms'] == 'DAP'

    def test_origin_country_default_kr(self):
        items = [{'description': 'Pouch', 'category': 'pouch',
                  'quantity': 1, 'unit_value': Decimal('20'), 'currency': 'USD'}]
        inv = doc_helper.generate_invoice_data(items, 'US', self._sender, self._receiver)
        assert inv['items'][0]['origin_country'] == 'KR'
        assert inv['items'][0]['hs_code'] == '4202.92'  # pouch HS code from HS_CODE_MAP

    def test_unknown_category_fallback_hs_code(self):
        items = [{'description': 'Mystery Item', 'category': 'unknown',
                  'quantity': 1, 'unit_value': Decimal('10'), 'currency': 'USD'}]
        inv = doc_helper.generate_invoice_data(items, 'US', self._sender, self._receiver)
        assert inv['items'][0]['hs_code'] == '9999.99'  # fallback for unknown category


# ──────────────────────────────────────────────────────────
# Phase 27 — Shipping Tracking System Tests
# ──────────────────────────────────────────────────────────

from src.shipping.models import ShipmentStatus, ShipmentRecord, TrackingEvent  # noqa: E402
from src.shipping.carriers import (  # noqa: E402
    CJCarrier, HanjinCarrier, KoreaPostCarrier, CarrierFactory,
)
from src.shipping.tracker import ShipmentTracker  # noqa: E402


class TestShipmentStatusEnum:
    def test_shipment_status_enum(self):
        assert ShipmentStatus.picked_up.value == "picked_up"
        assert ShipmentStatus.in_transit.value == "in_transit"
        assert ShipmentStatus.out_for_delivery.value == "out_for_delivery"
        assert ShipmentStatus.delivered.value == "delivered"
        assert ShipmentStatus.exception.value == "exception"


class TestCarrierFactory:
    def test_carrier_factory_cj(self):
        carrier = CarrierFactory.get_carrier("cj")
        assert isinstance(carrier, CJCarrier)

    def test_carrier_factory_hanjin(self):
        carrier = CarrierFactory.get_carrier("hanjin")
        assert isinstance(carrier, HanjinCarrier)

    def test_carrier_factory_koreapost(self):
        carrier = CarrierFactory.get_carrier("koreapost")
        assert isinstance(carrier, KoreaPostCarrier)

    def test_carrier_mock_tracking(self):
        carrier = CarrierFactory.get_carrier("cj")
        record = carrier.track("1234567890")
        assert isinstance(record, ShipmentRecord)
        assert record.tracking_number == "1234567890"
        assert record.carrier == "cj"
        assert isinstance(record.status, ShipmentStatus)
        assert len(record.events) > 0
        assert all(isinstance(e, TrackingEvent) for e in record.events)


class TestShipmentTracker:
    def test_tracker_register(self):
        tracker = ShipmentTracker()
        record = tracker.register("9999999999", "hanjin", order_id="ORD-001")
        assert record.tracking_number == "9999999999"
        assert record.carrier == "hanjin"
        assert record.order_id == "ORD-001"

    def test_tracker_get_status(self):
        tracker = ShipmentTracker()
        tracker.register("8888888888", "cj")
        result = tracker.get_status("8888888888")
        assert result is not None
        assert result.tracking_number == "8888888888"

    def test_tracker_get_status_not_found(self):
        tracker = ShipmentTracker()
        assert tracker.get_status("NONEXISTENT") is None

    def test_tracker_update_status(self):
        tracker = ShipmentTracker()
        tracker.register("7777777777", "koreapost")
        updated = tracker.update_status("7777777777")
        assert updated is not None
        assert isinstance(updated.status, ShipmentStatus)

    def test_tracker_get_all(self):
        tracker = ShipmentTracker()
        tracker.register("1111111111", "cj")
        tracker.register("2222222222", "hanjin")
        all_records = tracker.get_all()
        assert len(all_records) == 2


class TestShippingApi:
    @pytest.fixture
    def shipping_client(self):
        from flask import Flask
        from src.api.shipping_api import shipping_api
        app = Flask(__name__)
        app.register_blueprint(shipping_api)
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    def test_shipping_api_status(self, shipping_client):
        resp = shipping_client.get("/api/v1/shipping/status_check")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_shipping_api_register(self, shipping_client):
        resp = shipping_client.post(
            "/api/v1/shipping/register",
            json={"tracking_number": "3333333333", "carrier": "cj", "order_id": "ORD-999"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["tracking_number"] == "3333333333"
        assert data["carrier"] == "cj"

    def test_shipping_api_register_missing_fields(self, shipping_client):
        resp = shipping_client.post("/api/v1/shipping/register", json={"carrier": "cj"})
        assert resp.status_code == 400

    def test_shipping_api_get_status(self, shipping_client):
        # Register first, then fetch via carrier query param
        resp = shipping_client.get(
            "/api/v1/shipping/status/4444444444?carrier=hanjin"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tracking_number"] == "4444444444"
