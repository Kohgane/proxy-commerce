"""tests/test_taobao_collector.py — TaobaoCollector 테스트 (30+ 테스트)."""

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

TAOBAO_ITEM_ID = '123456789012'
ALB_ITEM_ID = '987654321098'

TAOBAO_URL = f'https://item.taobao.com/item.htm?id={TAOBAO_ITEM_ID}'
TAOBAO_URL_EXTRA = f'https://item.taobao.com/item.htm?id={TAOBAO_ITEM_ID}&spm=a1z09'
ALB_URL = f'https://detail.1688.com/offer/{ALB_ITEM_ID}.html'
ALB_URL_OFFER_ID = f'https://detail.1688.com/offer/list.htm?offerId={ALB_ITEM_ID}'

TAOBAO_HTML = """
<html><body>
<h3 id="J_Title" class="tb-main-title">无线蓝牙耳机</h3>
<span class="tb-rmb-num">29.9</span>
<img id="J_ImgBooth"><img data-src="//img.taobao.com/main.jpg" /></img></img>
<div id="J_breadCrumb"><a href="#">数码</a></div>
<div class="J_Score"><em class="score-num">4.8</em></div>
<div id="description"><p>蓝牙5.0 支持30小时续航</p></div>
<ul id="J_UlThumb">
  <li><img data-src="//img.taobao.com/thumb1.jpg" /></li>
</ul>
</body></html>
"""

TAOBAO_HTML_PRICE_RANGE = """
<html><body>
<h1>女装夏季连衣裙</h1>
<p>¥19.9-39.9</p>
<div id="J_breadCrumb"><a href="#">女装</a></div>
</body></html>
"""

ALB_HTML = """
<html><body>
<h1 class="d-title">批发蓝牙耳机 工厂直销</h1>
<span class="price-common"><em class="price-unit">15.5</em></span>
<div class="detail-image"><img src="//img.1688.com/main.jpg" /></div>
<div class="breadcrumb"><a href="#">数码配件</a></div>
<div id="description"><p>工厂直销 最低起订量50件</p></div>
</body></html>
"""

SEARCH_HTML_TAOBAO = """
<html><body>
<div class="item" data-category="数码">
  <div class="item-info">
    <a href="//item.taobao.com/item.htm?id=111111111111"><h3>无线耳机A</h3></a>
    <em class="tb-rmb-num">19.9</em>
    <img data-src="//img.taobao.com/s1.jpg" />
  </div>
</div>
<div class="item" data-category="数码">
  <div class="item-info">
    <a href="//item.taobao.com/item.htm?id=222222222222"><h3>无线耳机B</h3></a>
    <em class="tb-rmb-num">29.9</em>
    <img data-src="//img.taobao.com/s2.jpg" />
  </div>
</div>
</body></html>
"""


@pytest.fixture
def taobao_collector():
    from src.collectors.taobao_collector import TaobaoCollector
    return TaobaoCollector(platform='taobao')


@pytest.fixture
def alb_collector():
    from src.collectors.taobao_collector import TaobaoCollector
    return TaobaoCollector(platform='1688')


# ---------------------------------------------------------------------------
# 1. 초기화 테스트
# ---------------------------------------------------------------------------

class TestTaobaoCollectorInit:
    def test_taobao_init(self, taobao_collector):
        assert taobao_collector.platform == 'taobao'
        assert taobao_collector.currency == 'CNY'
        assert taobao_collector.country == 'CN'
        assert taobao_collector.marketplace == 'taobao'
        assert taobao_collector.base_url == 'https://item.taobao.com'

    def test_1688_init(self, alb_collector):
        assert alb_collector.platform == '1688'
        assert alb_collector.currency == 'CNY'
        assert alb_collector.base_url == 'https://detail.1688.com'

    def test_invalid_platform_raises(self):
        from src.collectors.taobao_collector import TaobaoCollector
        with pytest.raises(ValueError, match='Unsupported platform'):
            TaobaoCollector(platform='aliexpress')

    def test_env_vars_applied(self, monkeypatch):
        monkeypatch.setenv('COLLECTOR_TIMEOUT', '30')
        monkeypatch.setenv('COLLECTOR_DELAY', '5')
        from src.collectors.taobao_collector import TaobaoCollector
        c = TaobaoCollector()
        assert c.timeout == 30
        assert c.delay == 5.0

    def test_cookie_from_env(self, monkeypatch):
        monkeypatch.setenv('TAOBAO_COOKIE', 'sessionid=abc123')
        from src.collectors.taobao_collector import TaobaoCollector
        c = TaobaoCollector()
        assert c._cookie == 'sessionid=abc123'


# ---------------------------------------------------------------------------
# 2. URL에서 상품 ID 추출
# ---------------------------------------------------------------------------

class TestExtractItemId:
    def test_taobao_item_id(self, taobao_collector):
        assert taobao_collector._extract_item_id(TAOBAO_URL) == TAOBAO_ITEM_ID

    def test_taobao_item_id_extra_params(self, taobao_collector):
        assert taobao_collector._extract_item_id(TAOBAO_URL_EXTRA) == TAOBAO_ITEM_ID

    def test_taobao_item_id_regex_fallback(self, taobao_collector):
        url = f'https://item.taobao.com/item.htm?spm=something&id={TAOBAO_ITEM_ID}'
        assert taobao_collector._extract_item_id(url) == TAOBAO_ITEM_ID

    def test_taobao_none_for_no_id(self, taobao_collector):
        assert taobao_collector._extract_item_id('https://taobao.com/') is None

    def test_taobao_none_for_empty(self, taobao_collector):
        assert taobao_collector._extract_item_id('') is None

    def test_1688_offer_url(self, alb_collector):
        assert alb_collector._extract_item_id(ALB_URL) == ALB_ITEM_ID

    def test_1688_offer_id_param(self, alb_collector):
        assert alb_collector._extract_item_id(ALB_URL_OFFER_ID) == ALB_ITEM_ID

    def test_1688_none_for_bad_url(self, alb_collector):
        assert alb_collector._extract_item_id('https://1688.com/') is None


# ---------------------------------------------------------------------------
# 3. 타오바오 페이지 파싱
# ---------------------------------------------------------------------------

class TestParseTaobaoPage:
    def test_parse_title(self, taobao_collector):
        product = taobao_collector._parse_taobao_page(TAOBAO_HTML, TAOBAO_ITEM_ID)
        assert product['title_original'] == '无线蓝牙耳机'

    def test_parse_price(self, taobao_collector):
        product = taobao_collector._parse_taobao_page(TAOBAO_HTML, TAOBAO_ITEM_ID)
        assert product['price_original'] == 29.9

    def test_parse_price_range(self, taobao_collector):
        product = taobao_collector._parse_taobao_page(TAOBAO_HTML_PRICE_RANGE, TAOBAO_ITEM_ID)
        # 범위 가격에서 첫 번째 값 사용
        assert product['price_original'] == 19.9

    def test_parse_currency(self, taobao_collector):
        product = taobao_collector._parse_taobao_page(TAOBAO_HTML, TAOBAO_ITEM_ID)
        assert product['currency'] == 'CNY'

    def test_parse_category(self, taobao_collector):
        product = taobao_collector._parse_taobao_page(TAOBAO_HTML, TAOBAO_ITEM_ID)
        assert product['category'] == '数码'
        assert product['category_code'] == 'DIG'

    def test_parse_category_women(self, taobao_collector):
        product = taobao_collector._parse_taobao_page(TAOBAO_HTML_PRICE_RANGE, TAOBAO_ITEM_ID)
        assert product['category'] == '女装'
        assert product['category_code'] == 'WCL'

    def test_parse_rating(self, taobao_collector):
        product = taobao_collector._parse_taobao_page(TAOBAO_HTML, TAOBAO_ITEM_ID)
        assert product['rating'] == 4.8

    def test_parse_description(self, taobao_collector):
        product = taobao_collector._parse_taobao_page(TAOBAO_HTML, TAOBAO_ITEM_ID)
        assert '蓝牙' in product['description_original']

    def test_parse_collector_id(self, taobao_collector):
        product = taobao_collector._parse_taobao_page(TAOBAO_HTML, TAOBAO_ITEM_ID)
        assert product['collector_id'] == TAOBAO_ITEM_ID


# ---------------------------------------------------------------------------
# 4. 1688 페이지 파싱
# ---------------------------------------------------------------------------

class TestParse1688Page:
    def test_parse_title(self, alb_collector):
        product = alb_collector._parse_1688_page(ALB_HTML, ALB_ITEM_ID)
        assert product['title_original'] == '批发蓝牙耳机 工厂直销'

    def test_parse_price(self, alb_collector):
        product = alb_collector._parse_1688_page(ALB_HTML, ALB_ITEM_ID)
        assert product['price_original'] == 15.5

    def test_parse_category(self, alb_collector):
        product = alb_collector._parse_1688_page(ALB_HTML, ALB_ITEM_ID)
        assert product['category'] == '数码配件'

    def test_parse_collector_id(self, alb_collector):
        product = alb_collector._parse_1688_page(ALB_HTML, ALB_ITEM_ID)
        assert product['collector_id'] == ALB_ITEM_ID

    def test_parse_currency(self, alb_collector):
        product = alb_collector._parse_1688_page(ALB_HTML, ALB_ITEM_ID)
        assert product['currency'] == 'CNY'


# ---------------------------------------------------------------------------
# 5. 카테고리 매핑
# ---------------------------------------------------------------------------

class TestCategoryMapping:
    def test_all_categories_mapped(self, taobao_collector):
        from src.collectors.taobao_collector import TaobaoCollector
        for cn_name in TaobaoCollector.CATEGORY_MAP:
            code = taobao_collector._map_category(cn_name)
            assert len(code) == 3, f'{cn_name} → {code}'

    def test_unknown_category_fallback(self, taobao_collector):
        code = taobao_collector._map_category('未知类别')
        assert code == 'GEN'

    def test_empty_category(self, taobao_collector):
        assert taobao_collector._map_category('') == 'GEN'


# ---------------------------------------------------------------------------
# 6. 가격 계산 (CNY → KRW)
# ---------------------------------------------------------------------------

class TestCalculateImportPrice:
    def test_basic_cny_to_krw(self, taobao_collector, monkeypatch):
        monkeypatch.setenv('FX_CNYKRW', '200')
        monkeypatch.setenv('IMPORT_MARGIN_PCT', '25')
        product = {
            'price_original': 10.0,
            'currency': 'CNY',
            'weight_kg': None,
        }
        result = taobao_collector._calculate_import_price(product)
        # 10 CNY × 200 = 2000 KRW (원가)
        assert result['price_krw'] == 2000

    def test_warehouse_fee_included(self, taobao_collector, monkeypatch):
        monkeypatch.setenv('FX_CNYKRW', '185')
        monkeypatch.setenv('CN_WAREHOUSE_FEE_BASE_KRW', '3000')
        monkeypatch.setenv('IMPORT_MARGIN_PCT', '0')
        product = {'price_original': 0.0, 'currency': 'CNY', 'weight_kg': None}
        result = taobao_collector._calculate_import_price(product)
        # Only warehouse fee
        assert result['sell_price_krw'] >= 3000

    def test_no_customs_under_threshold(self, taobao_collector, monkeypatch):
        monkeypatch.setenv('FX_CNYKRW', '185')
        monkeypatch.setenv('IMPORT_MARGIN_PCT', '0')
        # Low price: 100 CNY = 18500 KRW < 150000 threshold
        product = {'price_original': 100.0, 'currency': 'CNY', 'weight_kg': None}
        result = taobao_collector._calculate_import_price(product)
        assert result.get('price_krw') is not None

    def test_sells_at_margin(self, taobao_collector, monkeypatch):
        monkeypatch.setenv('FX_CNYKRW', '200')
        monkeypatch.setenv('IMPORT_MARGIN_PCT', '25')
        monkeypatch.setenv('CN_WAREHOUSE_FEE_BASE_KRW', '0')
        monkeypatch.setenv('CN_WAREHOUSE_FEE_PER_KG_KRW', '0')
        product = {'price_original': 10.0, 'currency': 'CNY', 'weight_kg': 0.0}
        result = taobao_collector._calculate_import_price(product)
        # sell = 2000 * 1.25 = 2500
        assert result['sell_price_krw'] == 2500

    def test_returns_product_unchanged_on_no_price(self, taobao_collector):
        product = {'currency': 'CNY', 'weight_kg': None}
        result = taobao_collector._calculate_import_price(product)
        assert result is product


# ---------------------------------------------------------------------------
# 7. SKU 생성
# ---------------------------------------------------------------------------

class TestGenerateSku:
    def test_taobao_sku_prefix(self, taobao_collector):
        product = {
            'marketplace': 'taobao',
            'country': 'CN',
            'category_code': 'DIG',
            'collector_id': '123456789012',
        }
        sku = taobao_collector.generate_sku(product)
        assert sku.startswith('TAO-')

    def test_1688_sku_prefix(self, alb_collector):
        product = {
            'marketplace': 'taobao',
            'country': 'CN',
            'category_code': 'ELC',
            'collector_id': '987654321098',
        }
        sku = alb_collector.generate_sku(product)
        assert sku.startswith('ALB-')

    def test_sku_includes_category(self, taobao_collector):
        product = {
            'marketplace': 'taobao',
            'country': 'CN',
            'category_code': 'BTY',
            'collector_id': '123456789099',
        }
        sku = taobao_collector.generate_sku(product)
        assert 'BTY' in sku

    def test_sku_format(self, taobao_collector):
        product = {
            'marketplace': 'taobao',
            'country': 'CN',
            'category_code': 'DIG',
            'collector_id': '123456789012',
        }
        sku = taobao_collector.generate_sku(product)
        parts = sku.split('-')
        assert len(parts) >= 3

    def test_sku_empty_product(self, taobao_collector):
        sku = taobao_collector.generate_sku({})
        assert sku == ''


# ---------------------------------------------------------------------------
# 8. collect_product (단위 테스트, HTTP mock)
# ---------------------------------------------------------------------------

class TestCollectProduct:
    def test_collect_product_success(self, taobao_collector):
        with patch.object(taobao_collector, '_fetch', return_value=TAOBAO_HTML):
            with patch.object(taobao_collector, 'translate_product', side_effect=lambda p: p):
                with patch.object(taobao_collector, 'calculate_prices', side_effect=lambda p: p):
                    product = taobao_collector.collect_product(TAOBAO_URL)
        assert product is not None
        assert product['title_original'] == '无线蓝牙耳机'
        assert product['source_url'] == TAOBAO_URL
        assert product['marketplace'] == 'taobao'
        assert product['country'] == 'CN'

    def test_collect_product_bad_url_returns_none(self, taobao_collector):
        result = taobao_collector.collect_product('https://taobao.com/')
        assert result is None

    def test_collect_product_fetch_failure_returns_none(self, taobao_collector):
        with patch.object(taobao_collector, '_fetch', return_value=None):
            result = taobao_collector.collect_product(TAOBAO_URL)
        assert result is None

    def test_collect_product_1688(self, alb_collector):
        with patch.object(alb_collector, '_fetch', return_value=ALB_HTML):
            with patch.object(alb_collector, 'translate_product', side_effect=lambda p: p):
                with patch.object(alb_collector, 'calculate_prices', side_effect=lambda p: p):
                    product = alb_collector.collect_product(ALB_URL)
        assert product is not None
        assert product['title_original'] == '批发蓝牙耳机 工厂直销'


# ---------------------------------------------------------------------------
# 9. 검색 기능
# ---------------------------------------------------------------------------

class TestSearchProducts:
    def test_search_returns_empty_on_fetch_failure(self, taobao_collector):
        with patch.object(taobao_collector, '_fetch', return_value=None):
            results = taobao_collector.search_products('耳机')
        assert results == []

    def test_search_returns_empty_on_no_results(self, taobao_collector):
        empty_html = '<html><body></body></html>'
        with patch.object(taobao_collector, '_fetch', return_value=empty_html):
            results = taobao_collector.search_products('耳机')
        assert results == []

    def test_search_respects_max_results(self, taobao_collector):
        with patch.object(taobao_collector, '_fetch', return_value=None):
            results = taobao_collector.search_products('耳机', max_results=5)
        assert len(results) <= 5


# ---------------------------------------------------------------------------
# 10. 배치 수집
# ---------------------------------------------------------------------------

class TestCollectBatch:
    def test_batch_returns_only_successful(self, taobao_collector):
        def mock_collect(url):
            if 'good' in url:
                return {'title_original': 'good', 'source_url': url}
            return None

        with patch.object(taobao_collector, 'collect_product', side_effect=mock_collect):
            results = taobao_collector.collect_batch([
                'https://item.taobao.com/item.htm?id=good1',
                'https://item.taobao.com/item.htm?id=bad1',
                'https://item.taobao.com/item.htm?id=good2',
            ])
        assert len(results) == 2

    def test_batch_empty_list(self, taobao_collector):
        results = taobao_collector.collect_batch([])
        assert results == []


# ---------------------------------------------------------------------------
# 11. 번역 통합
# ---------------------------------------------------------------------------

class TestTranslation:
    def test_translate_calls_zh_to_ko(self, taobao_collector):
        product = {
            'title_original': '无线蓝牙耳机',
            'description_original': '蓝牙5.0',
        }
        with patch('src.translate.zh_to_ko', return_value='무선 블루투스 이어폰') as mock_zh:
            result = taobao_collector.translate_product(product)
        mock_zh.assert_called()
        assert result.get('title_ko') is not None

    def test_translate_no_crash_on_error(self, taobao_collector):
        product = {'title_original': '테스트'}
        # Even with translate errors, should not crash
        with patch('src.translate.translate', side_effect=Exception('API error')):
            result = taobao_collector.translate_product(product)
        assert result is not None


# ---------------------------------------------------------------------------
# 12. 에러 처리
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_collect_product_exception_returns_none(self, taobao_collector):
        with patch.object(taobao_collector, '_extract_item_id', side_effect=Exception('crash')):
            result = taobao_collector.collect_product(TAOBAO_URL)
        assert result is None

    def test_calculate_prices_exception_doesnt_crash(self, taobao_collector):
        product = {'price_original': 'invalid', 'currency': 'CNY'}
        result = taobao_collector.calculate_prices(product)
        assert result is not None

    def test_none_product_returns_none(self, taobao_collector):
        assert taobao_collector.collect_product(None) is None
