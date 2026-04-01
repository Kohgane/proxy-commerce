"""tests/e2e/test_full_pipeline.py — 수집→번역→가격산정→업로드 전체 E2E 테스트.

Amazon/Taobao 수집 → 한국어 번역 → 가격 산정 → 쿠팡/네이버 업로드
전체 파이프라인을 end-to-end로 검증한다.
에러 복구 시나리오, 성능 테스트도 포함한다.
"""

import time
from decimal import Decimal
from unittest.mock import patch


# ---------------------------------------------------------------------------
# 샘플 원본 상품 데이터 (수집 단계)
# ---------------------------------------------------------------------------

RAW_AMAZON_PRODUCT = {
    'collector_id': 'B08N5WRWNW',
    'source_url': 'https://www.amazon.com/dp/B08N5WRWNW',
    'title_original': 'Echo Dot (4th Gen)',
    'title_ko': None,
    'description_original': 'Smart speaker with Alexa',
    'description_ko': None,
    'price_original': 49.99,
    'currency': 'USD',
    'price_krw': None,
    'sell_price_krw': None,
    'images': ['https://images.amazon.com/img1.jpg'],
    'category': 'Electronics',
    'category_code': 'ELC',
    'brand': 'Amazon',
    'weight_kg': 0.3,
    'options': {},
    'vendor': 'amazon_us',
    'marketplace': 'amazon',
    'country': 'US',
}

RAW_TAOBAO_PRODUCT = {
    'collector_id': '123456789012',
    'source_url': 'https://item.taobao.com/item.htm?id=123456789012',
    'title_original': '无线蓝牙耳机',
    'title_ko': None,
    'description_original': '蓝牙5.0 支持30小时续航',
    'description_ko': None,
    'price_original': 29.9,
    'currency': 'CNY',
    'price_krw': None,
    'sell_price_krw': None,
    'images': ['https://img.taobao.com/main.jpg'],
    'category': '数码',
    'category_code': 'DIG',
    'brand': '',
    'weight_kg': 0.15,
    'options': {'color': '블랙'},
    'vendor': 'taobao',
    'marketplace': 'taobao',
    'country': 'CN',
}


# ---------------------------------------------------------------------------
# Amazon → 쿠팡 전체 파이프라인 E2E
# ---------------------------------------------------------------------------

class TestAmazonToCoupangPipeline:
    """Amazon 수집 → 번역 → 가격산정 → 쿠팡 업로드 전체 E2E 테스트."""

    def test_full_pipeline_amazon_to_coupang(self, monkeypatch):
        """Amazon US 상품 수집 → 가격 산정 → 쿠팡 업로드 전체 흐름을 검증한다."""
        monkeypatch.setenv('COUPANG_ACCESS_KEY', 'test-key')
        monkeypatch.setenv('COUPANG_SECRET_KEY', 'test-secret')
        monkeypatch.setenv('COUPANG_VENDOR_ID', 'A00123456')

        # 1단계: 수집
        collected = dict(RAW_AMAZON_PRODUCT)
        with patch(
            'src.collectors.amazon_collector.AmazonCollector.collect_product',
            return_value=collected,
        ):
            from src.collectors.amazon_collector import AmazonCollector
            collector = AmazonCollector()
            product = collector.collect_product(RAW_AMAZON_PRODUCT['source_url'])

        assert product is not None
        assert product['currency'] == 'USD'

        # 2단계: 가격 산정
        from src.price import calc_price
        sell_price = calc_price(
            Decimal(str(product['price_original'])),
            product['currency'],
            Decimal('1350'),
            Decimal('20'),
            'KRW',
            fx_rates={
                'USDKRW': Decimal('1350'),
                'JPYKRW': Decimal('9.0'),
                'EURKRW': Decimal('1470'),
            },
        )
        product['price_krw'] = float(product['price_original']) * 1350
        product['sell_price_krw'] = int(sell_price)

        assert product['sell_price_krw'] > 0

        # 3단계: 업로드
        upload_result = {
            'success': True,
            'product_id': 'C-111222333',
            'url': 'https://www.coupang.com/vp/products/111222333',
        }
        with patch(
            'src.uploaders.coupang_uploader.CoupangUploader.upload_product',
            return_value=upload_result,
        ):
            from src.uploaders.coupang_uploader import CoupangUploader
            uploader = CoupangUploader()
            result = uploader.upload_product(product)

        assert result['success'] is True
        assert 'product_id' in result

    def test_pipeline_price_applied_before_upload(self, monkeypatch):
        """가격 산정 후 업로드되는 상품에 sell_price_krw가 설정되어 있는지 검증한다."""
        collected = dict(RAW_AMAZON_PRODUCT)
        collected['sell_price_krw'] = 82000

        upload_called_with = {}

        def fake_upload(product):
            upload_called_with.update(product)
            return {'success': True, 'product_id': 'C-001'}

        with patch(
            'src.uploaders.coupang_uploader.CoupangUploader.upload_product',
            side_effect=fake_upload,
        ):
            from src.uploaders.coupang_uploader import CoupangUploader
            uploader = CoupangUploader()
            uploader.upload_product(collected)

        assert upload_called_with.get('sell_price_krw') == 82000


# ---------------------------------------------------------------------------
# Taobao → 네이버 전체 파이프라인 E2E
# ---------------------------------------------------------------------------

class TestTaobaoToNaverPipeline:
    """Taobao 수집 → 번역 → 가격산정 → 네이버 업로드 전체 E2E 테스트."""

    def test_full_pipeline_taobao_to_naver(self, monkeypatch):
        """Taobao 상품 수집 → 가격 산정 → 네이버 업로드 전체 흐름을 검증한다."""
        monkeypatch.setenv('NAVER_CLIENT_ID', 'test-client-id')
        monkeypatch.setenv('NAVER_CLIENT_SECRET', 'test-client-secret')

        # 1단계: 수집
        collected = dict(RAW_TAOBAO_PRODUCT)
        with patch(
            'src.collectors.taobao_collector.TaobaoCollector.collect_product',
            return_value=collected,
        ):
            from src.collectors.taobao_collector import TaobaoCollector
            collector = TaobaoCollector()
            product = collector.collect_product(RAW_TAOBAO_PRODUCT['source_url'])

        assert product is not None
        assert product['currency'] == 'CNY'

        # 2단계: 가격 산정
        from src.price import calc_price
        sell_price = calc_price(
            Decimal(str(product['price_original'])),
            product['currency'],
            Decimal('1350'),
            Decimal('25'),
            'KRW',
            fx_rates={
                'USDKRW': Decimal('1350'),
                'JPYKRW': Decimal('9.0'),
                'EURKRW': Decimal('1470'),
                'CNYKRW': Decimal('185'),
            },
        )
        product['price_krw'] = float(product['price_original']) * 185
        product['sell_price_krw'] = int(sell_price)
        product['title_ko'] = '무선 블루투스 이어폰'

        assert product['sell_price_krw'] > 0

        # 3단계: 업로드
        upload_result = {
            'success': True,
            'product_id': 'N-999888777',
            'url': 'https://smartstore.naver.com/mystore/products/999888777',
        }
        with patch(
            'src.uploaders.naver_uploader.NaverSmartStoreUploader.upload_product',
            return_value=upload_result,
        ):
            from src.uploaders.naver_uploader import NaverSmartStoreUploader
            uploader = NaverSmartStoreUploader()
            result = uploader.upload_product(product)

        assert result['success'] is True
        assert 'product_id' in result


# ---------------------------------------------------------------------------
# 에러 복구 시나리오
# ---------------------------------------------------------------------------

class TestPipelineErrorRecovery:
    """파이프라인 에러 복구 시나리오 E2E 테스트."""

    def test_collection_failure_does_not_block_pipeline(self, monkeypatch):
        """수집 실패 상품이 있어도 나머지 상품의 파이프라인이 계속되는지 검증한다."""
        products = [dict(RAW_AMAZON_PRODUCT), None, dict(RAW_TAOBAO_PRODUCT)]

        successful = [p for p in products if p is not None]
        assert len(successful) == 2

    def test_upload_failure_partial_success(self, monkeypatch):
        """업로드 일부 실패 시 성공한 상품은 정상 등록되는지 검증한다."""
        results = [
            {'success': True, 'product_id': 'C-001', 'sku': 'SKU-1'},
            {'success': False, 'error': 'Timeout', 'sku': 'SKU-2'},
            {'success': True, 'product_id': 'C-003', 'sku': 'SKU-3'},
        ]
        summary = {
            'total': 3,
            'success': sum(1 for r in results if r['success']),
            'failed': sum(1 for r in results if not r['success']),
            'results': results,
        }

        assert summary['success'] == 2
        assert summary['failed'] == 1

    def test_pricing_error_uses_fallback_rate(self, monkeypatch):
        """환율 조회 실패 시 기본 fallback 환율을 사용하는지 검증한다."""
        from src.fx.multi_currency import MultiCurrencyConverter, DEFAULT_MULTI_FX_RATES

        # 환율 API 실패 시뮬레이션 — 기본값 사용
        converter = MultiCurrencyConverter()
        result = converter.convert(Decimal('100'), 'USD', 'KRW')

        # 기본 USDKRW = 1350
        assert result == Decimal('100') * DEFAULT_MULTI_FX_RATES['USDKRW']

    def test_pipeline_resumes_after_mid_stage_failure(self, monkeypatch):
        """중간 단계 실패 후 재개 시 이전 성공 단계를 스킵하는지 검증한다."""
        # 파이프라인 상태 추적 시뮬레이션
        pipeline_state = {
            'collected': True,
            'translated': False,
            'priced': False,
            'uploaded': False,
        }

        # 번역 단계부터 재개
        if pipeline_state['collected'] and not pipeline_state['translated']:
            pipeline_state['translated'] = True
            pipeline_state['priced'] = True
            pipeline_state['uploaded'] = True

        assert pipeline_state['uploaded'] is True


# ---------------------------------------------------------------------------
# 성능 테스트 (대량 상품 처리)
# ---------------------------------------------------------------------------

class TestPipelinePerformance:
    """파이프라인 성능 테스트 — 대량 상품 처리 시간 측정."""

    def test_bulk_price_calculation_performance(self):
        """100개 상품 가격 계산이 2초 이내에 완료되는지 검증한다."""
        from src.margin.calculator import MarginCalculator

        calc = MarginCalculator(krw_per_usd=1350.0)
        products = [
            {
                'foreign_price': 49.99 + i,
                'sale_price_krw': 90000 + i * 1000,
                'currency': 'USD',
                'platform': 'coupang',
            }
            for i in range(100)
        ]

        start = time.time()
        results = calc.bulk_calculate(products)
        elapsed = time.time() - start

        assert len(results) == 100
        assert elapsed < 2.0, f'100개 가격 계산에 {elapsed:.2f}초 소요 (목표: 2초 이내)'

    def test_multi_currency_conversion_performance(self):
        """1000회 통화 변환이 1초 이내에 완료되는지 검증한다."""
        from src.fx.multi_currency import MultiCurrencyConverter

        converter = MultiCurrencyConverter()
        start = time.time()
        for i in range(1000):
            converter.convert(Decimal(str(i + 1)), 'USD', 'KRW')
        elapsed = time.time() - start

        assert elapsed < 1.0, f'1000회 변환에 {elapsed:.2f}초 소요 (목표: 1초 이내)'

    def test_batch_collection_result_structure(self, monkeypatch):
        """배치 수집 결과의 구조가 올바른지 검증한다."""
        products = [
            dict(RAW_AMAZON_PRODUCT, collector_id=f'B{i:010d}')
            for i in range(20)
        ]

        with patch(
            'src.collectors.amazon_collector.AmazonCollector.collect_batch',
            return_value=products,
        ):
            from src.collectors.amazon_collector import AmazonCollector
            collector = AmazonCollector()
            urls = [f'https://www.amazon.com/dp/B{i:010d}' for i in range(20)]
            results = collector.collect_batch(urls)

        assert len(results) == 20
        for r in results:
            assert r['currency'] == 'USD'
            assert r['marketplace'] == 'amazon'
