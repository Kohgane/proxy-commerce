"""tests/test_shopify_markets.py — Phase 6-2 신규 모듈 테스트 (107개+).

커버리지:
- MultiCurrencyConverter: 모든 통화 쌍 변환, to_krw/from_krw, get_rate, 엣지 케이스
- ShopifyMarketsChannel: prepare_product() 다통화 가격, calc_country_prices() 13개국,
  export_batch(), get_shipping_options()
- InternationalRouter: route_international_order() 각 국가별, detect_country(),
  select_shipping_method(), generate_customs_documents(), calc_order_taxes()
- 통합 테스트: 카탈로그 행 → 다통화 가격 → 주문 → 국제 라우팅 → 세관서류 전체 플로우
"""
import json
import os
import sys
import tempfile
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.fx.multi_currency import MultiCurrencyConverter, DEFAULT_MULTI_FX_RATES  # noqa: E402
from src.channels.shopify_markets import ShopifyMarketsChannel  # noqa: E402
from src.orders.international_router import InternationalRouter  # noqa: E402

# ── 테스트용 고정 환율 ────────────────────────────────────────────────────────
FX = {
    'USDKRW': Decimal('1350'),
    'JPYKRW': Decimal('9.0'),
    'EURKRW': Decimal('1470'),
    'GBPKRW': Decimal('1710'),
    'THBKRW': Decimal('38'),
    'VNDKRW': Decimal('0.054'),
    'IDRKRW': Decimal('0.085'),
    'PHPKRW': Decimal('24'),
    'AEDKRW': Decimal('368'),
    'SARKRW': Decimal('360'),
    'SGDKRW': Decimal('1005'),
    'MYRKRW': Decimal('305'),
    'PLNKRW': Decimal('340'),
    'CNYKRW': Decimal('186'),
}

# ── 테스트용 샘플 카탈로그 행 ─────────────────────────────────────────────────
SAMPLE_ROW = {
    'sku': 'PTR-BAG-001',
    'status': 'active',
    'title_ko': '포터 탱커 백팩',
    'title_en': 'Porter Tanker Backpack',
    'category': 'bag',
    'brand': 'PORTER',
    'source_country': 'JP',
    'buy_price': '30000',
    'buy_currency': 'JPY',
    'stock': 5,
    'images': 'https://example.com/img1.jpg,https://example.com/img2.jpg',
}


# ── 테스트용 샘플 Shopify 주문 ────────────────────────────────────────────────
def _make_order(country_code: str, price: str = '100', currency: str = 'USD',
                grams: int = 500, quantity: int = 1) -> dict:
    return {
        'id': 12345,
        'order_number': '#1001',
        'email': 'test@example.com',
        'customer': {'first_name': 'Test', 'last_name': 'User', 'email': 'test@example.com'},
        'shipping_address': {
            'name': 'Test User',
            'address1': '123 Main St',
            'city': 'Test City',
            'zip': '12345',
            'country': 'Test Country',
            'country_code': country_code,
            'phone': '+1234567890',
        },
        'line_items': [
            {
                'sku': 'PTR-BAG-001',
                'title': 'Porter Tanker Backpack',
                'price': price,
                'currency': currency,
                'quantity': quantity,
                'grams': grams,
                'product_type': 'bag',
            }
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. MultiCurrencyConverter 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestMultiCurrencyConverterInit:
    def test_default_rates_loaded(self):
        conv = MultiCurrencyConverter()
        assert 'USDKRW' in conv.fx_rates
        assert 'GBPKRW' in conv.fx_rates

    def test_custom_rates_override(self):
        conv = MultiCurrencyConverter({'USDKRW': Decimal('1400')})
        assert conv.fx_rates['USDKRW'] == Decimal('1400')

    def test_custom_rates_merge_with_defaults(self):
        conv = MultiCurrencyConverter({'USDKRW': Decimal('1400')})
        assert 'GBPKRW' in conv.fx_rates

    def test_default_multi_fx_rates_keys(self):
        expected = {'USDKRW', 'JPYKRW', 'EURKRW', 'GBPKRW', 'THBKRW',
                    'VNDKRW', 'IDRKRW', 'PHPKRW', 'AEDKRW', 'SARKRW',
                    'SGDKRW', 'MYRKRW', 'PLNKRW', 'CNYKRW'}
        assert set(DEFAULT_MULTI_FX_RATES.keys()) == expected


class TestMultiCurrencyConverterGetRate:
    def setup_method(self):
        self.conv = MultiCurrencyConverter(FX)

    def test_usd_rate(self):
        assert self.conv.get_rate('USD') == Decimal('1350')

    def test_jpy_rate(self):
        assert self.conv.get_rate('JPY') == Decimal('9.0')

    def test_krw_rate_is_one(self):
        assert self.conv.get_rate('KRW') == Decimal('1')

    def test_gbp_rate(self):
        assert self.conv.get_rate('GBP') == Decimal('1710')

    def test_unsupported_currency_raises(self):
        with pytest.raises(ValueError, match='지원하지 않는 통화'):
            self.conv.get_rate('BTC')

    def test_case_insensitive(self):
        assert self.conv.get_rate('usd') == Decimal('1350')


class TestMultiCurrencyConverterToKrw:
    def setup_method(self):
        self.conv = MultiCurrencyConverter(FX)

    def test_usd_to_krw(self):
        result = self.conv.to_krw(Decimal('100'), 'USD')
        assert result == Decimal('135000')

    def test_jpy_to_krw(self):
        result = self.conv.to_krw(Decimal('10000'), 'JPY')
        assert result == Decimal('90000')

    def test_eur_to_krw(self):
        result = self.conv.to_krw(Decimal('100'), 'EUR')
        assert result == Decimal('147000')

    def test_gbp_to_krw(self):
        result = self.conv.to_krw(Decimal('100'), 'GBP')
        assert result == Decimal('171000')

    def test_krw_to_krw_noop(self):
        result = self.conv.to_krw(Decimal('1000'), 'KRW')
        assert result == Decimal('1000')

    def test_thb_to_krw(self):
        result = self.conv.to_krw(Decimal('1000'), 'THB')
        assert result == Decimal('38000')

    def test_zero_amount(self):
        result = self.conv.to_krw(Decimal('0'), 'USD')
        assert result == Decimal('0')


class TestMultiCurrencyConverterFromKrw:
    def setup_method(self):
        self.conv = MultiCurrencyConverter(FX)

    def test_krw_to_usd(self):
        result = self.conv.from_krw(Decimal('135000'), 'USD')
        assert result == Decimal('100')

    def test_krw_to_jpy(self):
        result = self.conv.from_krw(Decimal('90000'), 'JPY')
        assert result == Decimal('10000')

    def test_krw_to_krw_noop(self):
        result = self.conv.from_krw(Decimal('1000'), 'KRW')
        assert result == Decimal('1000')

    def test_krw_to_gbp(self):
        result = self.conv.from_krw(Decimal('171000'), 'GBP')
        assert result == Decimal('100')


class TestMultiCurrencyConverterConvert:
    def setup_method(self):
        self.conv = MultiCurrencyConverter(FX)

    def test_same_currency(self):
        result = self.conv.convert(Decimal('100'), 'USD', 'USD')
        assert result == Decimal('100')

    def test_usd_to_jpy(self):
        # 100 USD → 135000 KRW → / 9.0 = 15000 JPY
        result = self.conv.convert(Decimal('100'), 'USD', 'JPY')
        assert result == Decimal('15000')

    def test_jpy_to_usd(self):
        # 15000 JPY → 135000 KRW → / 1350 = 100 USD
        result = self.conv.convert(Decimal('15000'), 'JPY', 'USD')
        assert result == Decimal('100')

    def test_usd_to_gbp(self):
        # 100 USD → 135000 KRW → / 1710 GBP
        result = self.conv.convert(Decimal('100'), 'USD', 'GBP')
        expected = Decimal('135000') / Decimal('1710')
        assert result == expected

    def test_usd_to_krw(self):
        result = self.conv.convert(Decimal('100'), 'USD', 'KRW')
        assert result == Decimal('135000')

    def test_krw_to_usd(self):
        result = self.conv.convert(Decimal('135000'), 'KRW', 'USD')
        assert result == Decimal('100')

    def test_eur_to_gbp(self):
        # 100 EUR → 147000 KRW → / 1710 GBP
        result = self.conv.convert(Decimal('100'), 'EUR', 'GBP')
        expected = Decimal('147000') / Decimal('1710')
        assert result == expected

    def test_all_13_currencies_convertible(self):
        currencies = ['USD', 'JPY', 'EUR', 'GBP', 'THB', 'VND', 'IDR', 'PHP',
                      'AED', 'SAR', 'SGD', 'MYR', 'PLN', 'CNY']
        for c in currencies:
            result = self.conv.convert(Decimal('1000'), 'KRW', c)
            assert result > Decimal('0'), f'{c} 변환 실패'


class TestMultiCurrencyConverterSupportedCurrencies:
    def setup_method(self):
        self.conv = MultiCurrencyConverter(FX)

    def test_includes_krw(self):
        assert 'KRW' in self.conv.get_supported_currencies()

    def test_includes_all_13_plus_krw(self):
        supported = self.conv.get_supported_currencies()
        for c in ['USD', 'JPY', 'EUR', 'GBP', 'THB', 'VND', 'IDR',
                  'PHP', 'AED', 'SAR', 'SGD', 'MYR', 'PLN', 'CNY', 'KRW']:
            assert c in supported, f'{c} 미포함'

    def test_returns_sorted_list(self):
        supported = self.conv.get_supported_currencies()
        assert supported == sorted(supported)


class TestMultiCurrencyConverterCountryCurrencies:
    def test_returns_13_countries(self):
        conv = MultiCurrencyConverter()
        mapping = conv.get_country_currencies()
        assert len(mapping) == 13

    def test_us_is_usd(self):
        conv = MultiCurrencyConverter()
        assert conv.get_country_currencies()['US'] == 'USD'

    def test_jp_is_jpy(self):
        conv = MultiCurrencyConverter()
        assert conv.get_country_currencies()['JP'] == 'JPY'

    def test_gb_is_gbp(self):
        conv = MultiCurrencyConverter()
        assert conv.get_country_currencies()['GB'] == 'GBP'


# ══════════════════════════════════════════════════════════════════════════════
# 2. ShopifyMarketsChannel 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestShopifyMarketsChannelInit:
    def test_default_countries(self):
        ch = ShopifyMarketsChannel()
        assert 'US' in ch.target_countries
        assert 'GB' in ch.target_countries

    def test_custom_countries(self):
        ch = ShopifyMarketsChannel(target_countries=['JP', 'US', 'GB'])
        assert ch.target_countries == ['JP', 'US', 'GB']

    def test_channel_name(self):
        ch = ShopifyMarketsChannel()
        assert ch.channel_name == 'shopify_markets'


class TestShopifyMarketsCalcCountryPrices:
    def setup_method(self):
        self.ch = ShopifyMarketsChannel(
            target_countries=['US', 'GB', 'JP'],
            fx_rates=FX,
        )

    def test_returns_dict_for_all_targets(self):
        result = self.ch.calc_country_prices(
            buy_price=Decimal('30000'),
            buy_currency='JPY',
            margin_pct=Decimal('20'),
            fx_rates=FX,
        )
        assert 'US' in result
        assert 'GB' in result
        assert 'JP' in result

    def test_us_currency_is_usd(self):
        result = self.ch.calc_country_prices(
            buy_price=Decimal('30000'), buy_currency='JPY',
            margin_pct=Decimal('20'), fx_rates=FX,
        )
        assert result['US']['currency'] == 'USD'

    def test_gb_currency_is_gbp(self):
        result = self.ch.calc_country_prices(
            buy_price=Decimal('30000'), buy_currency='JPY',
            margin_pct=Decimal('20'), fx_rates=FX,
        )
        assert result['GB']['currency'] == 'GBP'

    def test_jp_currency_is_jpy(self):
        result = self.ch.calc_country_prices(
            buy_price=Decimal('30000'), buy_currency='JPY',
            margin_pct=Decimal('20'), fx_rates=FX,
        )
        assert result['JP']['currency'] == 'JPY'

    def test_gb_is_ddp(self):
        result = self.ch.calc_country_prices(
            buy_price=Decimal('30000'), buy_currency='JPY',
            margin_pct=Decimal('20'), fx_rates=FX,
        )
        assert result['GB']['incoterms'] == 'DDP'

    def test_us_is_dap(self):
        result = self.ch.calc_country_prices(
            buy_price=Decimal('30000'), buy_currency='JPY',
            margin_pct=Decimal('20'), fx_rates=FX,
        )
        assert result['US']['incoterms'] == 'DAP'

    def test_price_is_decimal(self):
        result = self.ch.calc_country_prices(
            buy_price=Decimal('30000'), buy_currency='JPY',
            margin_pct=Decimal('20'), fx_rates=FX,
        )
        assert isinstance(result['US']['price'], Decimal)

    def test_price_positive(self):
        result = self.ch.calc_country_prices(
            buy_price=Decimal('30000'), buy_currency='JPY',
            margin_pct=Decimal('20'), fx_rates=FX,
        )
        for code, info in result.items():
            assert info['price'] > Decimal('0'), f'{code} 가격이 0 이하'

    def test_13_countries(self):
        from src.shipping import SUPPORTED_COUNTRIES
        ch = ShopifyMarketsChannel(target_countries=SUPPORTED_COUNTRIES, fx_rates=FX)
        result = ch.calc_country_prices(
            buy_price=Decimal('30000'), buy_currency='JPY',
            margin_pct=Decimal('20'), fx_rates=FX,
        )
        assert len(result) == 13


class TestShopifyMarketsPrepareProduct:
    def setup_method(self):
        self.ch = ShopifyMarketsChannel(
            target_countries=['US', 'GB'],
            fx_rates=FX,
        )

    def test_returns_dict(self):
        result = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        assert isinstance(result, dict)

    def test_title_from_title_en(self):
        result = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        assert result['title'] == 'Porter Tanker Backpack'

    def test_title_fallback_to_ko(self):
        row = dict(SAMPLE_ROW)
        del row['title_en']
        result = self.ch.prepare_product(row, 89.99)
        assert result['title'] == '포터 탱커 백팩'

    def test_variant_price_set(self):
        result = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        assert result['variants'][0]['price'] == '89.99'

    def test_variant_sku_set(self):
        result = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        assert result['variants'][0]['sku'] == 'PTR-BAG-001'

    def test_country_prices_present(self):
        result = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        assert 'country_prices' in result

    def test_country_prices_has_us_and_gb(self):
        result = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        cp = result['country_prices']
        assert 'US' in cp
        assert 'GB' in cp

    def test_images_parsed(self):
        result = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        assert len(result['images']) == 2

    def test_metafields_include_country_prices_json(self):
        result = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        keys = [mf['key'] for mf in result['metafields']]
        assert 'country_prices_json' in keys

    def test_metafields_json_parseable(self):
        result = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        json_mf = next(mf for mf in result['metafields'] if mf['key'] == 'country_prices_json')
        parsed = json.loads(json_mf['value'])
        assert 'US' in parsed

    def test_zero_buy_price(self):
        row = dict(SAMPLE_ROW)
        row['buy_price'] = 0
        result = self.ch.prepare_product(row, 0.0)
        assert isinstance(result, dict)

    def test_images_as_list(self):
        row = dict(SAMPLE_ROW)
        row['images'] = ['https://example.com/a.jpg', 'https://example.com/b.jpg']
        result = self.ch.prepare_product(row, 89.99)
        assert len(result['images']) == 2


class TestShopifyMarketsExportBatch:
    def setup_method(self):
        self.ch = ShopifyMarketsChannel(
            target_countries=['US', 'GB'],
            fx_rates=FX,
        )
        self.products = [self.ch.prepare_product(SAMPLE_ROW, 89.99)]

    def test_export_to_file(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        try:
            result = self.ch.export_batch(self.products, path)
            assert result == path
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            assert isinstance(data, list)
            assert len(data) == 1
        finally:
            os.unlink(path)

    def test_export_json_country_prices_serialized(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        try:
            self.ch.export_batch(self.products, path)
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            cp = data[0]['country_prices']
            assert isinstance(cp['US']['price'], str)
        finally:
            os.unlink(path)


class TestShopifyMarketsGetShippingOptions:
    def setup_method(self):
        self.ch = ShopifyMarketsChannel()

    def test_us_returns_list(self):
        result = self.ch.get_shipping_options('US')
        assert isinstance(result, list)
        assert len(result) > 0

    def test_jp_cheapest_flag(self):
        result = self.ch.get_shipping_options('JP')
        cheapest_items = [o for o in result if o['is_cheapest']]
        assert len(cheapest_items) >= 1

    def test_gb_fastest_flag(self):
        result = self.ch.get_shipping_options('GB')
        fastest_items = [o for o in result if o['is_fastest']]
        assert len(fastest_items) >= 1

    def test_has_required_keys(self):
        result = self.ch.get_shipping_options('US')
        for opt in result:
            assert 'method' in opt
            assert 'cost_krw' in opt
            assert 'delivery_days_min' in opt
            assert 'delivery_days_max' in opt
            assert 'tracking' in opt

    def test_custom_weight(self):
        result = self.ch.get_shipping_options('JP', weight_kg=Decimal('2.0'))
        assert all(o['cost_krw'] > Decimal('0') for o in result)

    def test_get_category_mapping(self):
        ch = ShopifyMarketsChannel()
        assert ch.get_category_mapping('bag') == 'bag'
        assert ch.get_category_mapping('perfume') == 'perfume'


# ══════════════════════════════════════════════════════════════════════════════
# 3. InternationalRouter 테스트
# ══════════════════════════════════════════════════════════════════════════════

class TestInternationalRouterDetectCountry:
    def setup_method(self):
        self.router = InternationalRouter()

    def test_us_order(self):
        order = _make_order('US')
        assert self.router.detect_country(order) == 'US'

    def test_gb_order(self):
        order = _make_order('GB')
        assert self.router.detect_country(order) == 'GB'

    def test_jp_order(self):
        order = _make_order('JP')
        assert self.router.detect_country(order) == 'JP'

    def test_lowercase_code(self):
        order = _make_order('us')
        assert self.router.detect_country(order) == 'US'

    def test_missing_country_raises(self):
        order = {'shipping_address': {}}
        with pytest.raises(ValueError, match='배송 국가 코드'):
            self.router.detect_country(order)

    def test_unsupported_country_raises(self):
        order = _make_order('KR')  # KR is not in SUPPORTED_COUNTRIES
        with pytest.raises(ValueError):
            self.router.detect_country(order)

    def test_no_shipping_address(self):
        order = {}
        with pytest.raises(ValueError):
            self.router.detect_country(order)


class TestInternationalRouterSelectShipping:
    def setup_method(self):
        self.router = InternationalRouter()

    def test_us_cheapest(self):
        result = self.router.select_shipping_method('US', Decimal('0.5'), prefer='cheapest')
        assert 'method' in result
        assert result['cost_krw'] > Decimal('0')

    def test_us_fastest(self):
        result = self.router.select_shipping_method('US', Decimal('0.5'), prefer='fastest')
        assert 'method' in result

    def test_jp_cheapest_cheaper_than_ems(self):
        cheapest = self.router.select_shipping_method('JP', Decimal('0.5'), prefer='cheapest')
        fastest = self.router.select_shipping_method('JP', Decimal('0.5'), prefer='fastest')
        assert cheapest['cost_krw'] <= fastest['cost_krw']

    def test_zero_weight_defaults_to_half_kg(self):
        result = self.router.select_shipping_method('GB', Decimal('0'), prefer='cheapest')
        assert result['cost_krw'] > Decimal('0')

    def test_has_required_keys(self):
        result = self.router.select_shipping_method('TH', Decimal('1.0'))
        for key in ('method', 'cost_krw', 'delivery_days_min', 'delivery_days_max', 'tracking'):
            assert key in result

    def test_heavy_weight_costs_more(self):
        light = self.router.select_shipping_method('US', Decimal('0.5'))
        heavy = self.router.select_shipping_method('US', Decimal('2.0'))
        assert heavy['cost_krw'] > light['cost_krw']


class TestInternationalRouterCalcOrderTaxes:
    def setup_method(self):
        self.router = InternationalRouter()

    def test_us_no_vat(self):
        order = _make_order('US', price='50', currency='USD')
        result = self.router.calc_order_taxes(order, 'US')
        assert result['country_code'] == 'US'
        assert isinstance(result['total_tax_local'], Decimal)

    def test_gb_has_tax(self):
        # £500 order → above £135 de minimis → duty + VAT
        order = _make_order('GB', price='500', currency='GBP')
        result = self.router.calc_order_taxes(order, 'GB')
        assert result['total_tax_local'] > Decimal('0')

    def test_returns_items_list(self):
        order = _make_order('JP', price='5000', currency='JPY')
        result = self.router.calc_order_taxes(order, 'JP')
        assert 'items' in result
        assert isinstance(result['items'], list)

    def test_incoterms_present(self):
        order = _make_order('US', price='100', currency='USD')
        result = self.router.calc_order_taxes(order, 'US')
        assert 'incoterms' in result
        assert result['incoterms'] in ('DAP', 'DDP')

    def test_de_minimis_flag(self):
        order = _make_order('US', price='100', currency='USD')
        result = self.router.calc_order_taxes(order, 'US')
        assert 'de_minimis_exempt' in result

    def test_empty_order_no_crash(self):
        order = {'line_items': [], 'shipping_address': {'country_code': 'US'}}
        result = self.router.calc_order_taxes(order, 'US')
        assert result['total_tax_local'] == Decimal('0')


class TestInternationalRouterGenerateCustomsDocs:
    def setup_method(self):
        self.router = InternationalRouter()

    def test_us_invoice_structure(self):
        order = _make_order('US')
        result = self.router.generate_customs_documents(order, 'US')
        assert 'invoice_number' in result
        assert 'items' in result
        assert 'incoterms' in result

    def test_invoice_number_format(self):
        order = _make_order('GB')
        result = self.router.generate_customs_documents(order, 'GB')
        assert result['invoice_number'].startswith('INV-')

    def test_receiver_name_from_shipping_address(self):
        order = _make_order('JP')
        result = self.router.generate_customs_documents(order, 'JP')
        assert result['receiver']['name'] == 'Test User'

    def test_items_have_hs_code(self):
        order = _make_order('US')
        result = self.router.generate_customs_documents(order, 'US')
        assert len(result['items']) > 0
        for item in result['items']:
            assert 'hs_code' in item

    def test_empty_line_items_no_crash(self):
        order = {
            'id': 1,
            'line_items': [],
            'customer': {},
            'shipping_address': {'country_code': 'US', 'name': 'Test'},
        }
        result = self.router.generate_customs_documents(order, 'US')
        assert 'invoice_number' in result


class TestInternationalRouterRouteOrder:
    def setup_method(self):
        self.router = InternationalRouter()

    def test_us_route(self):
        order = _make_order('US')
        result = self.router.route_international_order(order)
        assert result['country_code'] == 'US'
        assert result['incoterms'] == 'DAP'

    def test_gb_route_ddp(self):
        order = _make_order('GB')
        result = self.router.route_international_order(order)
        assert result['country_code'] == 'GB'
        assert result['incoterms'] == 'DDP'

    def test_jp_route(self):
        order = _make_order('JP')
        result = self.router.route_international_order(order)
        assert result['country_code'] == 'JP'

    def test_result_has_required_keys(self):
        order = _make_order('US')
        result = self.router.route_international_order(order)
        required = ('country_code', 'country_config', 'shipping_method',
                    'tax_detail', 'customs_invoice', 'incoterms',
                    'total_shipping_krw', 'total_tax_local')
        for key in required:
            assert key in result, f'키 없음: {key}'

    def test_shipping_krw_positive(self):
        order = _make_order('US')
        result = self.router.route_international_order(order)
        assert result['total_shipping_krw'] > Decimal('0')

    def test_country_config_type(self):
        from src.shipping import CountryConfig
        order = _make_order('GB')
        result = self.router.route_international_order(order)
        assert isinstance(result['country_config'], CountryConfig)

    def test_pl_route_ddp(self):
        order = _make_order('PL')
        result = self.router.route_international_order(order)
        assert result['incoterms'] == 'DDP'

    def test_th_route_dap(self):
        order = _make_order('TH')
        result = self.router.route_international_order(order)
        assert result['incoterms'] == 'DAP'


# ══════════════════════════════════════════════════════════════════════════════
# 4. 통합 테스트: 카탈로그 → 다통화 → 주문 → 라우팅
# ══════════════════════════════════════════════════════════════════════════════

class TestIntegrationFlow:
    """카탈로그 행 → 다통화 가격 → 주문 → 국제 라우팅 → 세관서류 전체 플로우."""

    def setup_method(self):
        from src.shipping import SUPPORTED_COUNTRIES
        self.ch = ShopifyMarketsChannel(
            target_countries=SUPPORTED_COUNTRIES,
            fx_rates=FX,
        )
        self.router = InternationalRouter()

    def test_full_flow_us(self):
        # 1. 카탈로그 → 다통화 상품 준비
        product = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        assert 'country_prices' in product
        assert 'US' in product['country_prices']

        # 2. 주문 생성 → 라우팅
        order = _make_order('US', price='89.99')
        route = self.router.route_international_order(order)
        assert route['country_code'] == 'US'
        assert route['incoterms'] == 'DAP'

    def test_full_flow_gb(self):
        product = self.ch.prepare_product(SAMPLE_ROW, 79.99)
        assert product['country_prices']['GB']['currency'] == 'GBP'

        order = _make_order('GB', price='79.99', currency='GBP')
        route = self.router.route_international_order(order)
        assert route['incoterms'] == 'DDP'

    def test_full_flow_jp(self):
        product = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        assert product['country_prices']['JP']['currency'] == 'JPY'

        order = _make_order('JP', price='12800', currency='JPY')
        route = self.router.route_international_order(order)
        assert route['country_code'] == 'JP'

    def test_multicurrency_converter_in_channel(self):
        conv = self.ch.fx_converter
        # JPY 30000 → KRW
        krw = conv.to_krw(Decimal('30000'), 'JPY')
        assert krw == Decimal('270000')  # 30000 * 9.0

    def test_all_13_countries_produce_prices(self):
        product = self.ch.prepare_product(SAMPLE_ROW, 89.99)
        cp = product['country_prices']
        from src.shipping import SUPPORTED_COUNTRIES
        for code in SUPPORTED_COUNTRIES:
            assert code in cp, f'{code} 국가 가격 없음'

    def test_customs_doc_in_route(self):
        order = _make_order('GB', price='500', currency='GBP')
        route = self.router.route_international_order(order)
        inv = route['customs_invoice']
        assert inv['incoterms'] == 'DDP'
        assert inv['invoice_number'].startswith('INV-')

    def test_export_batch_then_route(self):
        products = [self.ch.prepare_product(SAMPLE_ROW, 89.99)]
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        try:
            result_path = self.ch.export_batch(products, path)
            with open(result_path, encoding='utf-8') as f:
                data = json.load(f)
            assert len(data) == 1

            order = _make_order('US')
            route = self.router.route_international_order(order)
            assert route['country_code'] == 'US'
        finally:
            os.unlink(path)
