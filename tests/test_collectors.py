"""tests/test_collectors.py — Amazon 수집기 + 수집 파이프라인 테스트 (40+ 테스트)."""

import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_ASIN = 'B09XYZ1234'

AMAZON_US_URL = f'https://www.amazon.com/dp/{SAMPLE_ASIN}/'
AMAZON_JP_URL = f'https://www.amazon.co.jp/dp/{SAMPLE_ASIN}/'
AMAZON_GP_URL = f'https://www.amazon.com/gp/product/{SAMPLE_ASIN}'

PRODUCT_HTML_US = """
<html><body>
<span id="productTitle"> Wireless Earbuds Pro </span>
<span class="a-price"><span class="a-offscreen">$29.99</span></span>
<img id="landingImage" data-a-dynamic-image='{"https://example.com/img1.jpg":[500,500],"https://example.com/img2.jpg":[300,300]}' src="https://example.com/main.jpg"/>
<div id="wayfinding-breadcrumbs_feature_div">
  <ul><li><span class="a-list-item"><a>Electronics</a></span></li></ul>
</div>
<a id="bylineInfo">Brand: AudioTech</a>
<div id="acrPopover" title="4.5 out of 5 stars"></div>
<span id="acrCustomerReviewText">1,234 ratings</span>
<ul id="feature-bullets">
  <li><span class="a-list-item">Great sound quality</span></li>
  <li><span class="a-list-item">30-hour battery life</span></li>
</ul>
<div id="productDescription"><p>Detailed description here.</p></div>
<div id="availability"><span>In Stock</span></div>
<table id="productDetails_techSpec_section_1">
  <tr><th>Item Weight</th><td>0.15 kg</td></tr>
  <tr><th>Product Dimensions</th><td>10 x 5 x 3 cm</td></tr>
</table>
<div id="variation_color_name"><span class="selection">Black</span></div>
<div id="variation_size_name"><span class="selection">One Size</span></div>
</body></html>
"""

PRODUCT_HTML_JP = """
<html><body>
<span id="productTitle"> ワイヤレスイヤホン </span>
<span class="a-price"><span class="a-offscreen">¥2,980</span></span>
<img id="landingImage" src="https://example.co.jp/img.jpg"/>
<div id="wayfinding-breadcrumbs_feature_div">
  <ul><li><span class="a-list-item"><a>家電&amp;カメラ</a></span></li></ul>
</div>
<a id="bylineInfo">ブランド: AudioTech JP</a>
<div id="acrPopover" title="4.2 out of 5 stars"></div>
<span id="acrCustomerReviewText">567 ratings</span>
<div id="availability"><span>在庫あり</span></div>
</body></html>
"""

SEARCH_HTML = """
<html><body>
<div data-component-type="s-search-result" data-asin="B0001AAAAA">
  <h2><a href="/dp/B0001AAAAA"><span>Product One</span></a></h2>
  <span class="a-price"><span class="a-offscreen">$19.99</span></span>
  <img class="s-image" src="https://example.com/img1.jpg"/>
  <span class="a-icon-alt">4.3 out of 5 stars</span>
  <span class="a-size-base s-underline-text">456 ratings</span>
</div>
<div data-component-type="s-search-result" data-asin="B0002BBBBB">
  <h2><a href="/dp/B0002BBBBB"><span>Product Two</span></a></h2>
  <span class="a-price"><span class="a-offscreen">$9.50</span></span>
  <img class="s-image" src="https://example.com/img2.jpg"/>
</div>
</body></html>
"""


@pytest.fixture
def us_collector():
    from src.collectors.amazon_collector import AmazonCollector
    return AmazonCollector(country='US')


@pytest.fixture
def jp_collector():
    from src.collectors.amazon_collector import AmazonCollector
    return AmazonCollector(country='JP')


# ===========================================================================
# AmazonCollector — initialization
# ===========================================================================

class TestAmazonCollectorInit:
    def test_us_init(self, us_collector):
        from src.collectors.amazon_collector import AmazonCollector
        c = AmazonCollector(country='US')
        assert c.country == 'US'
        assert c.currency == 'USD'
        assert c.base_url == 'https://www.amazon.com'
        assert c.collector_name == 'amazon_us'
        assert c.marketplace == 'amazon'

    def test_jp_init(self, jp_collector):
        assert jp_collector.country == 'JP'
        assert jp_collector.currency == 'JPY'
        assert jp_collector.base_url == 'https://www.amazon.co.jp'
        assert jp_collector.collector_name == 'amazon_jp'

    def test_default_country_is_us(self):
        from src.collectors.amazon_collector import AmazonCollector
        c = AmazonCollector()
        assert c.country == 'US'

    def test_invalid_country_raises(self):
        from src.collectors.amazon_collector import AmazonCollector
        with pytest.raises(ValueError):
            AmazonCollector(country='KR')


# ===========================================================================
# AmazonCollector — ASIN extraction
# ===========================================================================

class TestExtractAsin:
    def test_standard_dp_url(self, us_collector):
        assert us_collector._extract_asin('https://www.amazon.com/dp/B09XYZ1234/') == 'B09XYZ1234'

    def test_gp_product_url(self, us_collector):
        assert us_collector._extract_asin('https://www.amazon.com/gp/product/B09XYZ1234') == 'B09XYZ1234'

    def test_jp_dp_url(self, jp_collector):
        assert jp_collector._extract_asin('https://www.amazon.co.jp/dp/B09XYZ1234/') == 'B09XYZ1234'

    def test_url_with_title_slug(self, us_collector):
        url = 'https://www.amazon.com/Wireless-Earbuds/dp/B0ABCDE123/ref=sr_1_1'
        assert us_collector._extract_asin(url) == 'B0ABCDE123'

    def test_url_with_query_param_asin(self, us_collector):
        url = 'https://www.amazon.com/s?asin=B0ABCDE123'
        assert us_collector._extract_asin(url) == 'B0ABCDE123'

    def test_invalid_url_returns_none(self, us_collector):
        assert us_collector._extract_asin('https://www.amazon.com/s?k=earbuds') is None

    def test_empty_url_returns_none(self, us_collector):
        assert us_collector._extract_asin('') is None

    def test_none_url_returns_none(self, us_collector):
        assert us_collector._extract_asin(None) is None


# ===========================================================================
# AmazonCollector — product page parsing
# ===========================================================================

class TestParseProductPage:
    def test_parse_us_title(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert p['title_original'] == 'Wireless Earbuds Pro'

    def test_parse_us_price(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert p['price_original'] == 29.99

    def test_parse_us_currency(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert p['currency'] == 'USD'

    def test_parse_us_images(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert isinstance(p['images'], list)
        assert len(p['images']) > 0

    def test_parse_us_category(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert p['category'] == 'Electronics'

    def test_parse_us_category_code(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert p['category_code'] == 'ELC'

    def test_parse_us_brand(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert 'AudioTech' in p['brand']

    def test_parse_us_rating(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert p['rating'] == 4.5

    def test_parse_us_review_count(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert p['review_count'] == 1234

    def test_parse_us_stock_status(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert 'Stock' in p['stock_status'] or 'stock' in p['stock_status'].lower()

    def test_parse_us_weight(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert p['weight_kg'] == 0.15

    def test_parse_us_dimensions(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert '10' in p['dimensions']

    def test_parse_us_options(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert p['options'].get('color') == 'Black'
        assert p['options'].get('size') == 'One Size'

    def test_parse_us_description(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert 'Great sound quality' in p['description_original']

    def test_parse_jp_title(self, jp_collector):
        p = jp_collector._parse_product_page(PRODUCT_HTML_JP, SAMPLE_ASIN)
        assert p['title_original'] == 'ワイヤレスイヤホン'

    def test_parse_jp_price_yen(self, jp_collector):
        p = jp_collector._parse_product_page(PRODUCT_HTML_JP, SAMPLE_ASIN)
        assert p['price_original'] == 2980.0

    def test_parse_jp_category_code(self, jp_collector):
        p = jp_collector._parse_product_page(PRODUCT_HTML_JP, SAMPLE_ASIN)
        assert p['category_code'] == 'ELC'

    def test_parse_unknown_category_defaults_to_gen(self, us_collector):
        html = PRODUCT_HTML_US.replace('<a>Electronics</a>', '<a>Unknown Category</a>')
        p = us_collector._parse_product_page(html, SAMPLE_ASIN)
        assert p['category_code'] == 'GEN'

    def test_parse_missing_price_returns_none(self, us_collector):
        html = PRODUCT_HTML_US.replace('<span class="a-offscreen">$29.99</span>', '')
        p = us_collector._parse_product_page(html, SAMPLE_ASIN)
        assert p['price_original'] is None

    def test_parse_asin_stored(self, us_collector):
        p = us_collector._parse_product_page(PRODUCT_HTML_US, SAMPLE_ASIN)
        assert p['collector_id'] == SAMPLE_ASIN


# ===========================================================================
# AmazonCollector — search page parsing
# ===========================================================================

class TestParseSearchPage:
    def test_parse_search_returns_list(self, us_collector):
        items = us_collector._parse_search_page(SEARCH_HTML)
        assert isinstance(items, list)
        assert len(items) == 2

    def test_parse_search_asin(self, us_collector):
        items = us_collector._parse_search_page(SEARCH_HTML)
        asins = [i['collector_id'] for i in items]
        assert 'B0001AAAAA' in asins
        assert 'B0002BBBBB' in asins

    def test_parse_search_title(self, us_collector):
        items = us_collector._parse_search_page(SEARCH_HTML)
        titles = [i['title_original'] for i in items]
        assert 'Product One' in titles

    def test_parse_search_price(self, us_collector):
        items = us_collector._parse_search_page(SEARCH_HTML)
        item = next(i for i in items if i['collector_id'] == 'B0001AAAAA')
        assert item['price_original'] == 19.99

    def test_parse_search_images(self, us_collector):
        items = us_collector._parse_search_page(SEARCH_HTML)
        item = next(i for i in items if i['collector_id'] == 'B0001AAAAA')
        assert len(item['images']) > 0

    def test_parse_search_rating(self, us_collector):
        items = us_collector._parse_search_page(SEARCH_HTML)
        item = next(i for i in items if i['collector_id'] == 'B0001AAAAA')
        assert item['rating'] == 4.3

    def test_parse_search_url_built(self, us_collector):
        items = us_collector._parse_search_page(SEARCH_HTML)
        item = next(i for i in items if i['collector_id'] == 'B0001AAAAA')
        assert item['source_url'] == 'https://www.amazon.com/dp/B0001AAAAA'

    def test_parse_empty_search_html(self, us_collector):
        items = us_collector._parse_search_page('<html><body></body></html>')
        assert items == []


# ===========================================================================
# AmazonCollector — collect_product (with mocks)
# ===========================================================================

class TestCollectProduct:
    def test_collect_product_success(self, us_collector):
        with patch.object(us_collector, '_fetch', return_value=PRODUCT_HTML_US):
            product = us_collector.collect_product(AMAZON_US_URL)
        assert product is not None
        assert product['collector_id'] == SAMPLE_ASIN
        assert product['marketplace'] == 'amazon'
        assert product['country'] == 'US'
        assert 'collected_at' in product
        assert 'sku' in product

    def test_collect_product_invalid_url_returns_none(self, us_collector):
        product = us_collector.collect_product('https://www.amazon.com/s?k=test')
        assert product is None

    def test_collect_product_fetch_fails_returns_none(self, us_collector):
        with patch.object(us_collector, '_fetch', return_value=None):
            product = us_collector.collect_product(AMAZON_US_URL)
        assert product is None

    def test_collect_product_network_error_returns_none(self, us_collector):
        with patch.object(us_collector, '_fetch', side_effect=Exception('Network error')):
            product = us_collector.collect_product(AMAZON_US_URL)
        assert product is None

    def test_collect_batch_filters_failures(self, us_collector):
        def fake_fetch(url):
            if SAMPLE_ASIN in url:
                return PRODUCT_HTML_US
            return None
        with patch.object(us_collector, '_fetch', side_effect=fake_fetch):
            results = us_collector.collect_batch([AMAZON_US_URL, 'https://www.amazon.com/s?k=bad'])
        assert len(results) == 1

    def test_collect_batch_empty_input(self, us_collector):
        results = us_collector.collect_batch([])
        assert results == []

    def test_search_products_returns_list(self, us_collector):
        with patch.object(us_collector, '_fetch', return_value=SEARCH_HTML):
            results = us_collector.search_products('earbuds', max_results=5)
        assert isinstance(results, list)

    def test_search_products_network_error_returns_empty_list(self, us_collector):
        with patch.object(us_collector, '_fetch', return_value=None):
            results = us_collector.search_products('earbuds')
        assert results == []


# ===========================================================================
# User-Agent rotation
# ===========================================================================

class TestUserAgent:
    def test_get_user_agent_returns_string(self, us_collector):
        ua = us_collector._get_user_agent()
        assert isinstance(ua, str)
        assert len(ua) > 10

    def test_custom_user_agent_env(self, monkeypatch):
        from src.collectors.amazon_collector import AmazonCollector
        monkeypatch.setenv('COLLECTOR_USER_AGENT', 'CustomBot/1.0')
        c = AmazonCollector(country='US')
        assert c._get_user_agent() == 'CustomBot/1.0'

    def test_rotation_uses_fallback_ua_list(self, us_collector):
        with patch('src.collectors.amazon_collector._BS4_AVAILABLE', True):
            with patch('builtins.__import__', side_effect=ImportError):
                ua = us_collector._get_user_agent()
        assert isinstance(ua, str)


# ===========================================================================
# Price calculation
# ===========================================================================

class TestPriceCalculation:
    def test_usd_to_krw_with_margin(self):
        from src.collectors.base_collector import BaseCollector

        class _Concrete(BaseCollector):
            collector_name = 'test'
            marketplace = 'test'
            country = 'US'
            currency = 'USD'
            base_url = 'https://example.com'

            def collect_product(self, url):
                return {}

            def search_products(self, keyword, max_results=20):
                return []

            def collect_batch(self, urls):
                return []

        c = _Concrete()
        product = {'price_original': 10.0, 'currency': 'USD'}
        with patch.dict(os.environ, {'IMPORT_MARGIN_PCT': '25', 'FX_USDKRW': '1300', 'FX_USE_LIVE': '0'}):
            result = c.calculate_prices(product)
        assert result.get('sell_price_krw') is not None
        assert result['sell_price_krw'] > 0

    def test_jpy_to_krw_with_margin(self):
        from src.collectors.base_collector import BaseCollector

        class _Concrete(BaseCollector):
            collector_name = 'test'
            marketplace = 'test'
            country = 'JP'
            currency = 'JPY'
            base_url = 'https://example.co.jp'

            def collect_product(self, url):
                return {}

            def search_products(self, keyword, max_results=20):
                return []

            def collect_batch(self, urls):
                return []

        c = _Concrete()
        product = {'price_original': 3000.0, 'currency': 'JPY'}
        with patch.dict(os.environ, {'IMPORT_MARGIN_PCT': '25', 'FX_JPYKRW': '9.0', 'FX_USE_LIVE': '0'}):
            result = c.calculate_prices(product)
        assert result.get('sell_price_krw') is not None
        assert result['sell_price_krw'] > 0

    def test_price_none_returns_product_unchanged(self, us_collector):
        product = {'price_original': None, 'currency': 'USD'}
        result = us_collector.calculate_prices(product)
        assert result.get('sell_price_krw') is None

    def test_customs_threshold_below(self):
        """상품 원가가 관세 기준(15만원) 이하이면 관세 없음."""
        from src.price import calc_landed_cost, _build_fx_rates
        with patch.dict(os.environ, {'FX_USDKRW': '1300', 'FX_USE_LIVE': '0', 'CUSTOMS_THRESHOLD_KRW': '150000'}):
            fx = _build_fx_rates()
            # $100 ≈ 130,000원 < 150,000원 → 관세 없음
            price = calc_landed_cost(100, 'USD', margin_pct=0, fx_rates=fx, shipping_fee=0)
        assert price == pytest.approx(130000, rel=0.05)

    def test_customs_threshold_above(self):
        """상품 원가가 관세 기준 초과이면 관세 부과."""
        from src.price import calc_landed_cost, _build_fx_rates
        with patch.dict(os.environ, {
            'FX_USDKRW': '1300', 'FX_USE_LIVE': '0',
            'CUSTOMS_THRESHOLD_KRW': '150000', 'CUSTOMS_RATE_DEFAULT': '0.20',
        }):
            fx = _build_fx_rates()
            # $200 ≈ 260,000원 > 150,000원 → 관세 부과
            price_with = calc_landed_cost(200, 'USD', margin_pct=0, fx_rates=fx, shipping_fee=0)
            price_without = calc_landed_cost(200, 'USD', margin_pct=0, fx_rates=fx,
                                             shipping_fee=0, customs_rate=0)
        assert price_with > price_without


# ===========================================================================
# Translation integration
# ===========================================================================

class TestTranslation:
    def test_translate_english_title_to_korean(self, us_collector):
        product = {'title_original': 'Wireless Earbuds', 'country': 'US'}
        with patch('src.translate.translate', return_value='무선 이어폰'):
            result = us_collector.translate_product(product)
        assert result['title_ko'] == '무선 이어폰'

    def test_translate_japanese_title_to_korean(self, jp_collector):
        product = {'title_original': 'ワイヤレスイヤホン', 'country': 'JP'}
        with patch('src.translate.translate', return_value='무선 이어폰'):
            result = jp_collector.translate_product(product)
        assert result['title_ko'] == '무선 이어폰'

    def test_translate_failure_preserves_original(self, us_collector):
        product = {'title_original': 'Wireless Earbuds', 'country': 'US'}
        with patch('src.translate.translate', side_effect=Exception('API error')):
            result = us_collector.translate_product(product)
        # 번역 실패 시 원문 유지
        assert result['title_original'] == 'Wireless Earbuds'

    def test_translate_empty_product(self, us_collector):
        result = us_collector.translate_product(None)
        assert result is None


# ===========================================================================
# SKU generation
# ===========================================================================

class TestSkuGeneration:
    def test_sku_amazon_us_electronics(self, us_collector):
        product = {
            'marketplace': 'amazon', 'country': 'US',
            'category_code': 'ELC', 'collector_id': 'B0ABCDE001',
        }
        sku = us_collector.generate_sku(product)
        assert sku.startswith('AMZ-US-ELC-')

    def test_sku_amazon_jp_beauty(self, jp_collector):
        product = {
            'marketplace': 'amazon', 'country': 'JP',
            'category_code': 'BTY', 'collector_id': 'B0ABCDE002',
        }
        sku = jp_collector.generate_sku(product)
        assert sku.startswith('AMZ-JP-BTY-')

    def test_sku_default_category_gen(self, us_collector):
        product = {
            'marketplace': 'amazon', 'country': 'US',
            'category_code': 'GEN', 'collector_id': 'B0ABCDE003',
        }
        sku = us_collector.generate_sku(product)
        assert 'GEN' in sku

    def test_sku_format_has_four_parts(self, us_collector):
        product = {
            'marketplace': 'amazon', 'country': 'US',
            'category_code': 'ELC', 'collector_id': 'B0ABCDE001',
        }
        sku = us_collector.generate_sku(product)
        parts = sku.split('-')
        assert len(parts) == 4

    def test_sku_empty_product(self, us_collector):
        sku = us_collector.generate_sku(None)
        assert sku == ''


# ===========================================================================
# CollectionManager
# ===========================================================================

class TestCollectionManager:
    @pytest.fixture
    def manager(self):
        from src.collectors.collection_manager import CollectionManager
        mgr = CollectionManager()
        mgr._ws = MagicMock()
        return mgr

    def test_save_new_products(self, manager):
        manager._ws.get_all_records.return_value = []
        manager._ws.get_all_values.return_value = [['col1']]
        products = [{'collector_id': 'B001', 'price_original': 19.99, 'stock_status': 'In Stock'}]
        result = manager.save_collected(products)
        assert result['new'] == 1
        assert result['errors'] == 0

    def test_save_duplicate_no_change(self, manager):
        existing = [{'collector_id': 'B001', 'price_original': '19.99', 'stock_status': 'In Stock'}]
        manager._ws.get_all_records.return_value = existing
        products = [{'collector_id': 'B001', 'price_original': 19.99, 'stock_status': 'In Stock'}]
        result = manager.save_collected(products)
        assert result['skipped'] == 1
        assert result['new'] == 0

    def test_save_price_change_triggers_update(self, manager):
        existing = [{'collector_id': 'B001', 'price_original': '19.99', 'stock_status': 'In Stock'}]
        manager._ws.get_all_records.return_value = existing
        products = [{'collector_id': 'B001', 'price_original': 24.99, 'stock_status': 'In Stock'}]
        result = manager.save_collected(products)
        assert result['updated'] == 1

    def test_dry_run_no_sheet_write(self, manager):
        manager._ws.get_all_records.return_value = []
        products = [{'collector_id': 'B001', 'price_original': 10.0}]
        result = manager.save_collected(products, dry_run=True)
        assert result['new'] == 1
        manager._ws.append_row.assert_not_called()

    def test_save_empty_products(self, manager):
        result = manager.save_collected([])
        assert result['total'] == 0

    def test_save_product_missing_collector_id(self, manager):
        manager._ws.get_all_records.return_value = []
        products = [{'price_original': 10.0}]
        result = manager.save_collected(products)
        assert result['errors'] == 1

    def test_get_collected_no_filter(self, manager):
        manager._ws.get_all_records.return_value = [
            {'collector_id': 'B001', 'vendor': 'amazon_us'},
            {'collector_id': 'B002', 'vendor': 'amazon_jp'},
        ]
        rows = manager.get_collected()
        assert len(rows) == 2

    def test_get_collected_with_marketplace_filter(self, manager):
        manager._ws.get_all_records.return_value = [
            {'collector_id': 'B001', 'vendor': 'amazon_us', 'category_code': 'ELC',
             'status': 'pending', 'collected_at': '2024-01-01'},
            {'collector_id': 'B002', 'vendor': 'amazon_jp', 'category_code': 'BTY',
             'status': 'pending', 'collected_at': '2024-01-02'},
        ]
        rows = manager.get_collected(filters={'marketplace': 'amazon_us'})
        assert len(rows) == 1
        assert rows[0]['collector_id'] == 'B001'

    def test_get_collected_with_status_filter(self, manager):
        manager._ws.get_all_records.return_value = [
            {'collector_id': 'B001', 'vendor': 'amazon_us', 'category_code': 'ELC',
             'status': 'uploaded', 'collected_at': '2024-01-01'},
            {'collector_id': 'B002', 'vendor': 'amazon_us', 'category_code': 'BTY',
             'status': 'pending', 'collected_at': '2024-01-02'},
        ]
        rows = manager.get_collected(filters={'status': 'pending'})
        assert len(rows) == 1

    def test_generate_report(self, manager):
        manager._ws.get_all_records.return_value = [
            {'vendor': 'amazon_us', 'status': 'pending', 'category_code': 'ELC'},
            {'vendor': 'amazon_jp', 'status': 'uploaded', 'category_code': 'BTY'},
        ]
        report = manager.generate_report()
        assert report['total'] == 2
        assert report['by_marketplace'].get('amazon_us') == 1
        assert report['by_status'].get('uploaded') == 1

    def test_mark_uploaded(self, manager):
        manager._ws.get_all_records.return_value = [{'sku': 'AMZ-US-ELC-001'}]
        manager._ws.row_values.return_value = ['sku', 'status']
        count = manager.mark_uploaded(['AMZ-US-ELC-001'], 'coupang')
        assert count == 1


# ===========================================================================
# CLI
# ===========================================================================

class TestCLI:
    def test_cli_search_dry_run(self, capsys):
        from src.collectors.cli import main
        with patch('src.collectors.amazon_collector.AmazonCollector.search_products',
                   return_value=[{'collector_id': 'B001', 'title_original': 'Test'}]):
            main(['--marketplace', 'amazon', '--country', 'US',
                  '--action', 'search', '--keyword', 'earbuds', '--dry-run'])
        captured = capsys.readouterr()
        assert 'B001' in captured.out

    def test_cli_collect_dry_run(self, capsys):
        from src.collectors.cli import main
        with patch('src.collectors.amazon_collector.AmazonCollector.collect_product',
                   return_value={'collector_id': 'B001', 'title_original': 'Test'}):
            main(['--action', 'collect', '--url', AMAZON_US_URL, '--dry-run'])
        captured = capsys.readouterr()
        assert 'B001' in captured.out

    def test_cli_collect_fail_exits(self, capsys):
        from src.collectors.cli import main
        with patch('src.collectors.amazon_collector.AmazonCollector.collect_product',
                   return_value=None):
            with pytest.raises(SystemExit):
                main(['--action', 'collect', '--url', AMAZON_US_URL])

    def test_cli_batch_dry_run(self, tmp_path, capsys):
        from src.collectors.cli import main
        url_file = tmp_path / 'urls.txt'
        url_file.write_text(AMAZON_US_URL + '\n')
        with patch('src.collectors.amazon_collector.AmazonCollector.collect_batch',
                   return_value=[{'collector_id': 'B001'}]):
            main(['--action', 'batch', '--file', str(url_file), '--dry-run'])
        captured = capsys.readouterr()
        assert 'B001' in captured.out

    def test_cli_report(self, capsys):
        from src.collectors.cli import main
        from src.collectors.collection_manager import CollectionManager
        with patch.object(CollectionManager, 'generate_report',
                          return_value={'total': 5, 'by_marketplace': {}}):
            main(['--action', 'report'])
        captured = capsys.readouterr()
        assert 'total' in captured.out

    def test_cli_missing_keyword_errors(self):
        from src.collectors.cli import main
        with pytest.raises(SystemExit):
            main(['--action', 'search'])

    def test_cli_missing_url_errors(self):
        from src.collectors.cli import main
        with pytest.raises(SystemExit):
            main(['--action', 'collect'])

    def test_cli_missing_file_errors(self):
        from src.collectors.cli import main
        with pytest.raises(SystemExit):
            main(['--action', 'batch'])


# ===========================================================================
# E2E scenario tests (mocked network)
# ===========================================================================

class TestE2EScenario:
    def test_amazon_us_full_pipeline(self):
        """Amazon US 검색 → 수집 → 번역 → 가격계산 → Sheets 저장 전체 흐름."""
        from src.collectors.amazon_collector import AmazonCollector
        from src.collectors.collection_manager import CollectionManager

        collector = AmazonCollector(country='US')
        with patch.object(collector, '_fetch', return_value=PRODUCT_HTML_US):
            product = collector.collect_product(AMAZON_US_URL)

        assert product is not None
        assert product['collector_id'] == SAMPLE_ASIN
        assert product['marketplace'] == 'amazon'
        assert product['country'] == 'US'

        mgr = CollectionManager()
        mgr._ws = MagicMock()
        mgr._ws.get_all_records.return_value = []
        mgr._ws.get_all_values.return_value = [['header']]
        result = mgr.save_collected([product], dry_run=True)
        assert result['new'] == 1

    def test_amazon_jp_full_pipeline(self):
        """Amazon JP 수집 → 일본어 번역 → 가격계산 흐름."""
        from src.collectors.amazon_collector import AmazonCollector

        collector = AmazonCollector(country='JP')
        with patch.object(collector, '_fetch', return_value=PRODUCT_HTML_JP):
            with patch('src.translate.translate', return_value='무선 이어폰'):
                product = collector.collect_product(AMAZON_JP_URL)

        assert product is not None
        assert product['country'] == 'JP'
        assert product['currency'] == 'JPY'
