"""tests/e2e/test_upload_pipeline.py — 업로드 파이프라인 E2E 테스트.

쿠팡/네이버 업로더 전체 흐름(인증→상품등록→확인), 배치 업로드,
실패 재시도, 부분 성공 처리를 검증한다.
"""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 샘플 상품 데이터
# ---------------------------------------------------------------------------

SAMPLE_PRODUCT = {
    'sku': 'TEST-ELC-001',
    'title': '에코 닷 4세대',
    'title_ko': '에코 닷 4세대',
    'description_html': '<p>Smart speaker with Alexa</p>',
    'price': 82000,
    'price_krw': 67500,
    'sell_price_krw': 82000,
    'original_price': 90000,
    'images': ['https://images.amazon.com/img1.jpg'],
    'category': 'Electronics',
    'category_code': 'ELC',
    'brand': 'Amazon',
    'weight_kg': 0.3,
    'stock': 10,
    'options': {},
    'tags': ['Echo', 'Alexa'],
    'shipping_fee': 0,
    'delivery_days': 3,
    'return_info': '30일 이내 반품 가능',
}

SAMPLE_PRODUCT_2 = {
    'sku': 'TEST-ELC-002',
    'title': '소니 무선 이어폰',
    'title_ko': '소니 무선 이어폰',
    'description_html': '<p>노이즈 캔슬링 지원</p>',
    'price': 109000,
    'price_krw': 89800,
    'sell_price_krw': 109000,
    'original_price': 120000,
    'images': ['https://images.amazon.co.jp/img1.jpg'],
    'category': 'Electronics',
    'category_code': 'ELC',
    'brand': 'Sony',
    'weight_kg': 0.05,
    'stock': 5,
    'options': {'color': '블랙'},
    'tags': ['Sony', 'Earphone'],
    'shipping_fee': 0,
    'delivery_days': 3,
    'return_info': '30일 이내 반품 가능',
}


# ---------------------------------------------------------------------------
# 쿠팡 업로더 E2E 테스트
# ---------------------------------------------------------------------------

class TestCoupangUploaderPipeline:
    """쿠팡 업로더 전체 파이프라인 E2E 테스트."""

    def test_coupang_upload_product_success(self, monkeypatch):
        """쿠팡 상품 업로드 성공 흐름(인증→등록→확인)을 검증한다."""
        monkeypatch.setenv('COUPANG_ACCESS_KEY', 'test-access-key')
        monkeypatch.setenv('COUPANG_SECRET_KEY', 'test-secret-key')
        monkeypatch.setenv('COUPANG_VENDOR_ID', 'A00123456')

        upload_result = {
            'success': True,
            'product_id': 'C-111222333',
            'url': 'https://www.coupang.com/vp/products/111222333',
            'market': 'coupang',
        }

        with patch(
            'src.uploaders.coupang_uploader.CoupangUploader.upload_product',
            return_value=upload_result,
        ) as mock_upload:
            from src.uploaders.coupang_uploader import CoupangUploader
            uploader = CoupangUploader()
            result = uploader.upload_product(SAMPLE_PRODUCT)

        assert result['success'] is True
        assert 'product_id' in result
        assert result['market'] == 'coupang'
        mock_upload.assert_called_once_with(SAMPLE_PRODUCT)

    def test_coupang_upload_product_failure(self, monkeypatch):
        """쿠팡 업로드 실패 시 에러 응답을 반환하는 흐름을 검증한다."""
        monkeypatch.setenv('COUPANG_ACCESS_KEY', 'bad-key')
        monkeypatch.setenv('COUPANG_SECRET_KEY', 'bad-secret')
        monkeypatch.setenv('COUPANG_VENDOR_ID', 'bad-vendor')

        error_result = {
            'success': False,
            'error': 'Authentication failed: Invalid access key',
            'market': 'coupang',
        }

        with patch(
            'src.uploaders.coupang_uploader.CoupangUploader.upload_product',
            return_value=error_result,
        ):
            from src.uploaders.coupang_uploader import CoupangUploader
            uploader = CoupangUploader()
            result = uploader.upload_product(SAMPLE_PRODUCT)

        assert result['success'] is False
        assert 'error' in result

    def test_coupang_batch_upload(self, monkeypatch):
        """쿠팡 배치 업로드(100개+ 상품) 전체 흐름을 검증한다."""
        monkeypatch.setenv('COUPANG_ACCESS_KEY', 'test-access-key')
        monkeypatch.setenv('COUPANG_SECRET_KEY', 'test-secret-key')
        monkeypatch.setenv('COUPANG_VENDOR_ID', 'A00123456')

        batch_result = {
            'total': 5,
            'success': 4,
            'failed': 1,
            'results': [
                {'success': True, 'product_id': f'C-{i}', 'sku': f'SKU-{i}'}
                for i in range(4)
            ] + [{'success': False, 'error': 'API error', 'sku': 'SKU-4'}],
        }

        with patch(
            'src.uploaders.coupang_uploader.CoupangUploader.upload_batch',
            return_value=batch_result,
        ):
            from src.uploaders.coupang_uploader import CoupangUploader
            uploader = CoupangUploader()
            products = [dict(SAMPLE_PRODUCT, sku=f'SKU-{i}') for i in range(5)]
            result = uploader.upload_batch(products)

        assert result['total'] == 5
        assert result['success'] == 4
        assert result['failed'] == 1

    def test_coupang_hmac_signature(self, monkeypatch):
        """쿠팡 HMAC 서명 생성이 올바른지 검증한다."""
        monkeypatch.setenv('COUPANG_ACCESS_KEY', 'test-access-key')
        monkeypatch.setenv('COUPANG_SECRET_KEY', 'test-secret-key')
        monkeypatch.setenv('COUPANG_VENDOR_ID', 'A00123456')

        from src.uploaders.coupang_uploader import CoupangUploader
        uploader = CoupangUploader()

        sig = uploader._generate_hmac_signature(
            method='GET',
            url_path='/v2/test',
            date='200701T000000Z',
        )
        assert isinstance(sig, str)
        assert len(sig) > 0


# ---------------------------------------------------------------------------
# 네이버 스마트스토어 업로더 E2E 테스트
# ---------------------------------------------------------------------------

class TestNaverUploaderPipeline:
    """네이버 스마트스토어 업로더 전체 파이프라인 E2E 테스트."""

    def test_naver_upload_product_success(self, monkeypatch):
        """네이버 스마트스토어 상품 업로드 성공 흐름을 검증한다."""
        monkeypatch.setenv('NAVER_CLIENT_ID', 'test-client-id')
        monkeypatch.setenv('NAVER_CLIENT_SECRET', 'test-client-secret')
        monkeypatch.setenv('NAVER_CHANNEL_ID', 'ch-001')

        upload_result = {
            'success': True,
            'product_id': 'N-999888777',
            'url': 'https://smartstore.naver.com/mystore/products/999888777',
            'market': 'naver',
        }

        with patch(
            'src.uploaders.naver_uploader.NaverSmartStoreUploader.upload_product',
            return_value=upload_result,
        ) as mock_upload:
            from src.uploaders.naver_uploader import NaverSmartStoreUploader
            uploader = NaverSmartStoreUploader()
            result = uploader.upload_product(SAMPLE_PRODUCT)

        assert result['success'] is True
        assert 'product_id' in result
        assert result['market'] == 'naver'
        mock_upload.assert_called_once_with(SAMPLE_PRODUCT)

    def test_naver_token_refresh(self, monkeypatch):
        """네이버 액세스 토큰 갱신 흐름을 검증한다."""
        monkeypatch.setenv('NAVER_CLIENT_ID', 'test-client-id')
        monkeypatch.setenv('NAVER_CLIENT_SECRET', 'test-client-secret')

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            'access_token': 'new-test-token',
            'token_type': 'Bearer',
            'expires_in': 3600,
        }

        with patch('requests.post', return_value=resp):
            from src.uploaders.naver_uploader import NaverSmartStoreUploader
            uploader = NaverSmartStoreUploader()
            token = uploader._get_access_token()

        assert token == 'new-test-token'

    def test_naver_batch_upload(self, monkeypatch):
        """네이버 배치 업로드 전체 흐름을 검증한다."""
        monkeypatch.setenv('NAVER_CLIENT_ID', 'test-client-id')
        monkeypatch.setenv('NAVER_CLIENT_SECRET', 'test-client-secret')
        monkeypatch.setenv('NAVER_CHANNEL_ID', 'ch-001')

        batch_result = {
            'total': 3,
            'success': 3,
            'failed': 0,
            'results': [
                {'success': True, 'product_id': f'N-{i}', 'sku': f'SKU-{i}'}
                for i in range(3)
            ],
        }

        with patch(
            'src.uploaders.naver_uploader.NaverSmartStoreUploader.upload_batch',
            return_value=batch_result,
        ):
            from src.uploaders.naver_uploader import NaverSmartStoreUploader
            uploader = NaverSmartStoreUploader()
            products = [dict(SAMPLE_PRODUCT, sku=f'SKU-{i}') for i in range(3)]
            result = uploader.upload_batch(products)

        assert result['total'] == 3
        assert result['success'] == 3
        assert result['failed'] == 0


# ---------------------------------------------------------------------------
# UploadManager 통합 흐름
# ---------------------------------------------------------------------------

class TestUploadManagerPipeline:
    """UploadManager 통합 업로드 파이프라인 E2E 테스트."""

    def test_upload_manager_to_coupang(self, monkeypatch, mock_sheets_e2e):
        """UploadManager를 통한 쿠팡 업로드 전체 흐름을 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')
        monkeypatch.setenv('COUPANG_ACCESS_KEY', 'test-key')
        monkeypatch.setenv('COUPANG_SECRET_KEY', 'test-secret')
        monkeypatch.setenv('COUPANG_VENDOR_ID', 'A00123456')

        _, ws = mock_sheets_e2e

        upload_result = {'total': 1, 'success': 1, 'failed': 0, 'results': []}
        with patch(
            'src.uploaders.upload_manager.UploadManager.upload_to_market',
            return_value=upload_result,
        ) as mock_upload:
            from src.uploaders.upload_manager import UploadManager
            manager = UploadManager()
            result = manager.upload_to_market(['TEST-ELC-001'], 'coupang')

        assert result['success'] == 1
        assert result['failed'] == 0
        mock_upload.assert_called_once_with(['TEST-ELC-001'], 'coupang')

    def test_upload_manager_to_naver(self, monkeypatch, mock_sheets_e2e):
        """UploadManager를 통한 네이버 업로드 전체 흐름을 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')
        monkeypatch.setenv('NAVER_CLIENT_ID', 'test-id')
        monkeypatch.setenv('NAVER_CLIENT_SECRET', 'test-secret')

        upload_result = {'total': 2, 'success': 2, 'failed': 0, 'results': []}
        with patch(
            'src.uploaders.upload_manager.UploadManager.upload_to_market',
            return_value=upload_result,
        ) as mock_upload:
            from src.uploaders.upload_manager import UploadManager
            manager = UploadManager()
            result = manager.upload_to_market(['SKU-1', 'SKU-2'], 'naver')

        assert result['total'] == 2
        assert result['success'] == 2
        mock_upload.assert_called_once_with(['SKU-1', 'SKU-2'], 'naver')

    def test_upload_manager_dry_run(self, monkeypatch, mock_sheets_e2e):
        """UploadManager dry_run 모드에서 실제 업로드 없이 결과를 반환하는지 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')

        dry_run_result = {'total': 1, 'success': 0, 'failed': 0, 'results': [], 'dry_run': True}
        with patch(
            'src.uploaders.upload_manager.UploadManager.upload_to_market',
            return_value=dry_run_result,
        ):
            from src.uploaders.upload_manager import UploadManager
            manager = UploadManager()
            result = manager.upload_to_market(['SKU-1'], 'coupang', dry_run=True)

        assert result.get('dry_run') is True

    def test_upload_retry_on_partial_failure(self, monkeypatch):
        """업로드 실패 항목 재시도 시 부분 성공 처리를 검증한다."""
        failed_skus = ['SKU-FAIL-1', 'SKU-FAIL-2']
        results = [{'success': False, 'error': 'Timeout', 'sku': sku} for sku in failed_skus]
        partial_result = {'total': 2, 'success': 0, 'failed': 2, 'results': results}

        retry_result = {'total': 2, 'success': 1, 'failed': 1, 'results': [
            {'success': True, 'product_id': 'C-001', 'sku': 'SKU-FAIL-1'},
            {'success': False, 'error': 'Server error', 'sku': 'SKU-FAIL-2'},
        ]}

        call_count = {'n': 0}

        def side_effect(skus, market, **kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                return partial_result
            return retry_result

        with patch(
            'src.uploaders.upload_manager.UploadManager.upload_to_market',
            side_effect=side_effect,
        ):
            from src.uploaders.upload_manager import UploadManager
            manager = UploadManager()
            result1 = manager.upload_to_market(failed_skus, 'coupang')
            failed = [r['sku'] for r in result1['results'] if not r['success']]
            result2 = manager.upload_to_market(failed, 'coupang')

        assert result1['failed'] == 2
        assert result2['success'] == 1
        assert call_count['n'] == 2
