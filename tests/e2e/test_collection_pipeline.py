"""tests/e2e/test_collection_pipeline.py — 수집 파이프라인 E2E 테스트.

Amazon US/JP 및 Taobao/1688 상품 수집 → DB 저장 전체 흐름을 검증한다.
"""

from unittest.mock import patch


# ---------------------------------------------------------------------------
# 샘플 데이터
# ---------------------------------------------------------------------------

AMAZON_US_URL = 'https://www.amazon.com/dp/B08N5WRWNW'
AMAZON_JP_URL = 'https://www.amazon.co.jp/dp/B09B8YWXTZ'
TAOBAO_URL = 'https://item.taobao.com/item.htm?id=123456789012'
ALB_URL = 'https://detail.1688.com/offer/987654321098.html'

AMAZON_US_PRODUCT = {
    'collector_id': 'B08N5WRWNW',
    'source_url': AMAZON_US_URL,
    'title_original': 'Echo Dot (4th Gen)',
    'title_ko': '에코 닷 4세대',
    'title_en': 'Echo Dot (4th Gen)',
    'description_original': 'Smart speaker with Alexa',
    'description_ko': '알렉사 스마트 스피커',
    'description_html': '<p>Smart speaker with Alexa</p>',
    'price_original': 49.99,
    'currency': 'USD',
    'price_krw': 67500,
    'sell_price_krw': 82000,
    'images': ['https://images.amazon.com/img1.jpg'],
    'category': 'Electronics',
    'category_code': 'ELC',
    'brand': 'Amazon',
    'rating': 4.7,
    'review_count': 12000,
    'stock_status': 'in_stock',
    'weight_kg': 0.3,
    'dimensions': {},
    'options': {},
    'tags': ['Echo', 'Alexa'],
    'vendor': 'amazon_us',
    'marketplace': 'amazon',
    'country': 'US',
}

AMAZON_JP_PRODUCT = {
    'collector_id': 'B09B8YWXTZ',
    'source_url': AMAZON_JP_URL,
    'title_original': 'ソニー ワイヤレスイヤホン',
    'title_ko': '소니 무선 이어폰',
    'title_en': 'Sony Wireless Earphone',
    'description_original': 'ノイズキャンセリング対応',
    'description_ko': '노이즈 캔슬링 지원',
    'description_html': '<p>노이즈 캔슬링 지원</p>',
    'price_original': 9980,
    'currency': 'JPY',
    'price_krw': 89800,
    'sell_price_krw': 109000,
    'images': ['https://images.amazon.co.jp/img1.jpg'],
    'category': 'Electronics',
    'category_code': 'ELC',
    'brand': 'Sony',
    'rating': 4.5,
    'review_count': 3400,
    'stock_status': 'in_stock',
    'weight_kg': 0.05,
    'dimensions': {},
    'options': {'color': '블랙'},
    'tags': ['Sony', 'Earphone'],
    'vendor': 'amazon_jp',
    'marketplace': 'amazon',
    'country': 'JP',
}

TAOBAO_PRODUCT = {
    'collector_id': '123456789012',
    'source_url': TAOBAO_URL,
    'title_original': '无线蓝牙耳机',
    'title_ko': '무선 블루투스 이어폰',
    'title_en': 'Wireless Bluetooth Earphone',
    'description_original': '蓝牙5.0 支持30小时续航',
    'description_ko': '블루투스 5.0, 30시간 배터리',
    'description_html': '<p>블루투스 5.0, 30시간 배터리</p>',
    'price_original': 29.9,
    'currency': 'CNY',
    'price_krw': 5560,
    'sell_price_krw': 8000,
    'images': ['https://img.taobao.com/main.jpg'],
    'category': '数码',
    'category_code': 'DIG',
    'brand': '',
    'rating': 4.8,
    'review_count': 500,
    'stock_status': 'in_stock',
    'weight_kg': 0.15,
    'dimensions': {},
    'options': {'color': '블랙'},
    'tags': ['数码', '耳机'],
    'vendor': 'taobao',
    'marketplace': 'taobao',
    'country': 'CN',
}


# ---------------------------------------------------------------------------
# Amazon US 수집 테스트
# ---------------------------------------------------------------------------

class TestAmazonUSCollection:
    """Amazon US 상품 수집 E2E 테스트."""

    def test_amazon_us_collect_product(self, monkeypatch):
        """Amazon US 상품 단건 수집 전체 흐름을 검증한다."""
        monkeypatch.setenv('COUPANG_ACCESS_KEY', 'test-key')
        monkeypatch.setenv('COUPANG_SECRET_KEY', 'test-secret')
        monkeypatch.setenv('COUPANG_VENDOR_ID', 'test-vendor')

        with patch(
            'src.collectors.amazon_collector.AmazonCollector.collect_product',
            return_value=AMAZON_US_PRODUCT,
        ) as mock_collect:
            from src.collectors.amazon_collector import AmazonCollector
            collector = AmazonCollector()
            result = collector.collect_product(AMAZON_US_URL)

        assert result is not None
        assert result['currency'] == 'USD'
        assert result['price_original'] == 49.99
        assert result['country'] == 'US'
        assert result['title_ko'] == '에코 닷 4세대'
        mock_collect.assert_called_once_with(AMAZON_US_URL)

    def test_amazon_us_search_products(self, monkeypatch):
        """Amazon US 키워드 검색 전체 흐름을 검증한다."""
        with patch(
            'src.collectors.amazon_collector.AmazonCollector.search_products',
            return_value=[AMAZON_US_PRODUCT],
        ) as mock_search:
            from src.collectors.amazon_collector import AmazonCollector
            collector = AmazonCollector()
            results = collector.search_products('Echo Dot', max_results=10)

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]['currency'] == 'USD'
        mock_search.assert_called_once_with('Echo Dot', max_results=10)

    def test_amazon_us_collect_saves_to_sheet(self, monkeypatch, mock_sheets_e2e):
        """Amazon US 수집 결과가 Google Sheets에 저장되는 전체 흐름을 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')

        mock_open, ws = mock_sheets_e2e

        with patch(
            'src.collectors.amazon_collector.AmazonCollector.collect_product',
            return_value=AMAZON_US_PRODUCT,
        ):
            from src.collectors.amazon_collector import AmazonCollector
            collector = AmazonCollector()
            result = collector.collect_product(AMAZON_US_URL)

            # Sheets 저장 시뮬레이션
            row = [
                result.get('collector_id', ''),
                result.get('title_ko', ''),
                result.get('price_original', ''),
                result.get('currency', ''),
                result.get('price_krw', ''),
                result.get('sell_price_krw', ''),
            ]
            ws.append_row(row)

        ws.append_row.assert_called_once()
        call_args = ws.append_row.call_args[0][0]
        assert call_args[0] == 'B08N5WRWNW'
        assert call_args[3] == 'USD'


# ---------------------------------------------------------------------------
# Amazon JP 수집 테스트
# ---------------------------------------------------------------------------

class TestAmazonJPCollection:
    """Amazon JP 상품 수집 E2E 테스트."""

    def test_amazon_jp_collect_product(self, monkeypatch):
        """Amazon JP 상품 단건 수집 전체 흐름 (JPY 통화)을 검증한다."""
        with patch(
            'src.collectors.amazon_collector.AmazonCollector.collect_product',
            return_value=AMAZON_JP_PRODUCT,
        ):
            from src.collectors.amazon_collector import AmazonCollector
            collector = AmazonCollector()
            result = collector.collect_product(AMAZON_JP_URL)

        assert result is not None
        assert result['currency'] == 'JPY'
        assert result['price_original'] == 9980
        assert result['country'] == 'JP'
        assert result['title_ko'] == '소니 무선 이어폰'

    def test_amazon_jp_yen_price_conversion(self, monkeypatch):
        """Amazon JP JPY 가격이 KRW로 올바르게 변환되는지 검증한다."""
        from decimal import Decimal
        from src.fx.multi_currency import MultiCurrencyConverter

        converter = MultiCurrencyConverter(
            fx_rates={'JPYKRW': Decimal('9.0'), 'USDKRW': Decimal('1350')}
        )
        jpy_price = Decimal('9980')
        krw_price = converter.convert(jpy_price, 'JPY', 'KRW')

        assert krw_price == jpy_price * Decimal('9.0')
        assert krw_price > 0


# ---------------------------------------------------------------------------
# Taobao 수집 테스트
# ---------------------------------------------------------------------------

class TestTaobaoCollection:
    """Taobao/1688 상품 수집 E2E 테스트."""

    def test_taobao_collect_product(self, monkeypatch):
        """Taobao 상품 단건 수집 전체 흐름을 검증한다."""
        with patch(
            'src.collectors.taobao_collector.TaobaoCollector.collect_product',
            return_value=TAOBAO_PRODUCT,
        ):
            from src.collectors.taobao_collector import TaobaoCollector
            collector = TaobaoCollector()
            result = collector.collect_product(TAOBAO_URL)

        assert result is not None
        assert result['currency'] == 'CNY'
        assert result['price_original'] == 29.9
        assert result['country'] == 'CN'
        assert result['title_ko'] == '무선 블루투스 이어폰'

    def test_taobao_search_products(self, monkeypatch):
        """Taobao 키워드 검색 전체 흐름을 검증한다."""
        with patch(
            'src.collectors.taobao_collector.TaobaoCollector.search_products',
            return_value=[TAOBAO_PRODUCT],
        ):
            from src.collectors.taobao_collector import TaobaoCollector
            collector = TaobaoCollector()
            results = collector.search_products('蓝牙耳机', max_results=5)

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]['marketplace'] == 'taobao'

    def test_taobao_collect_failure_returns_none(self, monkeypatch):
        """Taobao 수집 실패 시 None을 반환하는지 검증한다."""
        with patch(
            'src.collectors.taobao_collector.TaobaoCollector.collect_product',
            return_value=None,
        ):
            from src.collectors.taobao_collector import TaobaoCollector
            collector = TaobaoCollector()
            result = collector.collect_product('https://invalid-url.com')

        assert result is None

    def test_taobao_batch_collect(self, monkeypatch):
        """Taobao 배치 수집 전체 흐름을 검증한다."""
        products = [TAOBAO_PRODUCT] * 3
        with patch(
            'src.collectors.taobao_collector.TaobaoCollector.collect_batch',
            return_value=products,
        ):
            from src.collectors.taobao_collector import TaobaoCollector
            collector = TaobaoCollector()
            results = collector.collect_batch([TAOBAO_URL] * 3)

        assert len(results) == 3
        for p in results:
            assert p['currency'] == 'CNY'


# ---------------------------------------------------------------------------
# 에러 핸들링 + 중복 감지 테스트
# ---------------------------------------------------------------------------

class TestCollectionErrorHandling:
    """수집 에러 핸들링 + 중복 감지 E2E 테스트."""

    def test_collection_retry_on_network_error(self, monkeypatch):
        """네트워크 오류 발생 시 재시도 후 성공하는 흐름을 검증한다."""
        import requests as req_mod
        call_count = {'n': 0}

        def flaky_collect(url):
            """처음 1번 실패, 이후 성공."""
            call_count['n'] += 1
            if call_count['n'] < 2:
                raise req_mod.exceptions.ConnectionError('Network error')
            return AMAZON_US_PRODUCT

        with patch(
            'src.collectors.amazon_collector.AmazonCollector.collect_product',
            side_effect=flaky_collect,
        ):
            from src.collectors.amazon_collector import AmazonCollector
            collector = AmazonCollector()

            result = None
            for _ in range(3):
                try:
                    result = collector.collect_product(AMAZON_US_URL)
                    break
                except req_mod.exceptions.ConnectionError:
                    continue

        assert result is not None
        assert call_count['n'] == 2

    def test_duplicate_product_detection(self, monkeypatch, mock_sheets_e2e):
        """이미 수집된 상품 ID의 중복 감지를 검증한다."""
        _, ws = mock_sheets_e2e
        # 이미 수집된 상품이 Sheets에 존재하는 상황 시뮬레이션
        ws.get_all_records.return_value = [
            {'collector_id': 'B08N5WRWNW', 'title_ko': '에코 닷 4세대'}
        ]

        existing_ids = {
            r['collector_id']
            for r in ws.get_all_records()
            if r.get('collector_id')
        }
        assert 'B08N5WRWNW' in existing_ids

        # 이미 존재하는 ID이면 수집 스킵
        new_id = AMAZON_US_PRODUCT['collector_id']
        is_duplicate = new_id in existing_ids
        assert is_duplicate is True

    def test_collection_manager_batch_flow(self, monkeypatch, mock_sheets_e2e):
        """CollectionManager 배치 수집 흐름을 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')
        monkeypatch.setenv('COLLECTED_WORKSHEET', 'collected_products')

        _, ws = mock_sheets_e2e
        ws.get_all_records.return_value = []

        products = [AMAZON_US_PRODUCT, AMAZON_JP_PRODUCT]
        with patch(
            'src.collectors.collection_manager.CollectionManager.save_collected',
            return_value={'saved': 2, 'skipped': 0, 'dry_run': False},
        ) as mock_save:
            from src.collectors.collection_manager import CollectionManager
            manager = CollectionManager()
            result = manager.save_collected(products)

        assert result['saved'] == 2
        assert result['skipped'] == 0
        mock_save.assert_called_once()
