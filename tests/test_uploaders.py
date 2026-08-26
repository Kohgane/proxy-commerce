# v87-S7: 이 모듈들이 relay_request(단일 관문)를 타면서 직결도 requests.request로 나간다.
#   그래서 목 대상도 requests.post/get → requests.request 로 옮긴다(동작 동일, 경로만 통일).
"""tests/test_uploaders.py — 업로더 테스트 (40+ 테스트)."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_COLLECTED = {
    'sku': 'TAO-DIG-012',
    'title_original': '无线蓝牙耳机',
    'title_ko': '무선 블루투스 이어폰',
    'description_html': '<p>좋은 이어폰</p>',
    'price_krw': 8000,
    'sell_price_krw': 12000,
    'images': [
        'https://img.taobao.com/img1.jpg',
        'https://img.taobao.com/img2.jpg',
    ],
    'category': '数码',
    'category_code': 'DIG',
    'brand': 'SomeBrand',
    'origin': '중국',                # 제조국(고시정보 실값) — 미확인 시 등록 보류(P3)
    'weight_kg': 0.15,
    'options': {'color': '블랙'},
    'tags': ['数码', '耳机'],
}


@pytest.fixture
def coupang_uploader(monkeypatch):
    monkeypatch.setenv('COUPANG_ACCESS_KEY', 'test-access-key')
    monkeypatch.setenv('COUPANG_SECRET_KEY', 'test-secret-key')
    monkeypatch.setenv('COUPANG_VENDOR_ID', 'test-vendor')
    # 출고지/반품지 Wing 배송정보(필수) — 등록 전 사전검증 통과용
    monkeypatch.setenv('COUPANG_VENDOR_USER_ID', 'wing_user')
    monkeypatch.setenv('COUPANG_RETURN_CENTER_CODE', '1000274592')
    monkeypatch.setenv('COUPANG_OUTBOUND_SHIPPING_PLACE_CODE', '7437895')
    monkeypatch.setenv('COUPANG_RETURN_ZIP_CODE', '06000')
    monkeypatch.setenv('COUPANG_RETURN_ADDRESS', '서울시 강남구 테헤란로 1')
    monkeypatch.setenv('COUPANG_RETURN_CHARGE_NAME', '반품담당')
    monkeypatch.setenv('COUPANG_COMPANY_CONTACT_NUMBER', '02-1234-5678')
    # 택배사 코드(카나리 6차 거부 대응) — 이제 필수 설정. 유효 코드는 쿠팡 목록이 정본.
    monkeypatch.setenv('COUPANG_DELIVERY_COMPANY_CODE', 'EPOST')
    from src.uploaders.coupang_uploader import CoupangUploader
    return CoupangUploader()


@pytest.fixture
def naver_uploader(monkeypatch):
    monkeypatch.setenv('NAVER_CLIENT_ID', 'test-client-id')
    monkeypatch.setenv('NAVER_CLIENT_SECRET', 'test-client-secret')
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    return NaverSmartStoreUploader()


@pytest.fixture
def upload_manager():
    from src.uploaders.upload_manager import UploadManager
    return UploadManager()


# ===========================================================================
# Part I: BaseUploader
# ===========================================================================

class TestBaseUploader:
    def test_upload_fields_defined(self):
        from src.uploaders.base_uploader import BaseUploader
        assert 'sku' in BaseUploader.UPLOAD_FIELDS
        assert 'title' in BaseUploader.UPLOAD_FIELDS
        assert 'price' in BaseUploader.UPLOAD_FIELDS

    def test_prepare_product_basic(self, coupang_uploader):
        result = coupang_uploader.prepare_product(SAMPLE_COLLECTED)
        assert result['sku'] == 'TAO-DIG-012'
        assert result['images'] == SAMPLE_COLLECTED['images']

    def test_upload_batch_success(self, coupang_uploader):
        mock_upload = MagicMock(return_value={'success': True, 'product_id': '999'})
        coupang_uploader.upload_product = mock_upload
        products = [{'sku': 'A'}, {'sku': 'B'}]
        result = coupang_uploader.upload_batch(products)
        assert result['total'] == 2
        assert result['success'] == 2
        assert result['failed'] == 0

    def test_upload_batch_partial_failure(self, coupang_uploader):
        def mock_upload(product):
            if product.get('sku') == 'FAIL':
                return {'success': False, 'error': 'API error'}
            return {'success': True, 'product_id': '1'}

        coupang_uploader.upload_product = mock_upload
        products = [{'sku': 'OK'}, {'sku': 'FAIL'}]
        result = coupang_uploader.upload_batch(products)
        assert result['total'] == 2
        assert result['success'] == 1
        assert result['failed'] == 1

    def test_upload_batch_empty(self, coupang_uploader):
        result = coupang_uploader.upload_batch([])
        assert result['total'] == 0
        assert result['success'] == 0
        assert result['failed'] == 0


# ===========================================================================
# Part II: CoupangUploader
# ===========================================================================

class TestCoupangUploaderInit:
    def test_init_reads_env(self, monkeypatch):
        monkeypatch.setenv('COUPANG_ACCESS_KEY', 'ak')
        monkeypatch.setenv('COUPANG_SECRET_KEY', 'sk')
        monkeypatch.setenv('COUPANG_VENDOR_ID', 'vid')
        from src.uploaders.coupang_uploader import CoupangUploader
        u = CoupangUploader()
        assert u.access_key == 'ak'
        assert u.secret_key == 'sk'
        assert u.vendor_id == 'vid'

    def test_init_logs_warning_on_missing_keys(self, monkeypatch, caplog):
        monkeypatch.delenv('COUPANG_ACCESS_KEY', raising=False)
        monkeypatch.delenv('COUPANG_SECRET_KEY', raising=False)
        monkeypatch.delenv('COUPANG_VENDOR_ID', raising=False)
        import logging
        from src.uploaders.coupang_uploader import CoupangUploader
        with caplog.at_level(logging.WARNING):
            CoupangUploader()
        assert any('COUPANG' in r.message for r in caplog.records)


class TestCoupangPrepareProduct:
    def test_title_prefix(self, coupang_uploader):
        result = coupang_uploader.prepare_product(SAMPLE_COLLECTED)
        assert result['title'].startswith('[해외직구]')

    def test_title_max_50_chars(self, coupang_uploader):
        long_collected = dict(SAMPLE_COLLECTED)
        long_collected['title_ko'] = 'A' * 100
        result = coupang_uploader.prepare_product(long_collected)
        assert len(result['title']) <= 50

    def test_price_round_up_100(self, coupang_uploader):
        collected = dict(SAMPLE_COLLECTED, sell_price_krw=12050)
        result = coupang_uploader.prepare_product(collected)
        # 12050 → 12100 (100원 단위 올림)
        assert result['price'] == 12100

    def test_price_already_divisible(self, coupang_uploader):
        collected = dict(SAMPLE_COLLECTED, sell_price_krw=12000)
        result = coupang_uploader.prepare_product(collected)
        assert result['price'] == 12000

    def test_category_mapped(self, coupang_uploader):
        result = coupang_uploader.prepare_product(SAMPLE_COLLECTED)
        assert result['category_id'] == '76001'  # DIG → 76001

    def test_images_max_10(self, coupang_uploader):
        collected = dict(SAMPLE_COLLECTED, images=[f'http://img{i}.jpg' for i in range(15)])
        result = coupang_uploader.prepare_product(collected)
        assert len(result['images']) <= 10

    def test_delivery_days(self, coupang_uploader):
        result = coupang_uploader.prepare_product(SAMPLE_COLLECTED)
        assert result['delivery_days'] == '7-14'

    def test_return_info(self, coupang_uploader):
        result = coupang_uploader.prepare_product(SAMPLE_COLLECTED)
        assert '반품' in result['return_info']

    def test_empty_product_returns_empty(self, coupang_uploader):
        result = coupang_uploader.prepare_product({})
        assert result == {}


class TestCoupangHmacSignature:
    def test_signature_is_hex_string(self, coupang_uploader):
        sig = coupang_uploader._generate_hmac_signature('GET', '/v2/test', '210101T000000Z')
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex = 64 chars

    def test_different_input_gives_different_sig(self, coupang_uploader):
        sig1 = coupang_uploader._generate_hmac_signature('GET', '/v2/a', '210101T000000Z')
        sig2 = coupang_uploader._generate_hmac_signature('POST', '/v2/b', '210101T000001Z')
        assert sig1 != sig2


class TestCoupangApiRequest:
    def test_returns_error_when_no_credentials(self, monkeypatch):
        monkeypatch.delenv('COUPANG_ACCESS_KEY', raising=False)
        monkeypatch.delenv('COUPANG_SECRET_KEY', raising=False)
        monkeypatch.delenv('COUPANG_VENDOR_ID', raising=False)
        from src.uploaders.coupang_uploader import CoupangUploader
        u = CoupangUploader()
        result = u._api_request('GET', '/test')
        assert 'error' in result

    def test_api_request_success(self, coupang_uploader):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'data': {'sellerProductId': '12345'}}
        with patch('requests.request', return_value=mock_resp):
            result = coupang_uploader._api_request('GET', '/v2/test')
        assert result == {'data': {'sellerProductId': '12345'}}

    def test_api_request_401_returns_error(self, coupang_uploader):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch('requests.request', return_value=mock_resp):
            result = coupang_uploader._api_request('GET', '/v2/test')
        assert 'error' in result
        assert '401' in result['error']

    def test_api_request_500_returns_error(self, coupang_uploader):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = 'Internal Server Error'
        with patch('requests.request', return_value=mock_resp):
            result = coupang_uploader._api_request('GET', '/v2/test')
        assert 'error' in result


class TestCoupangUploadProduct:
    def test_upload_product_success(self, coupang_uploader):
        prepared = coupang_uploader.prepare_product(SAMPLE_COLLECTED)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'data': {'sellerProductId': '99999'}}
        with patch('requests.request', return_value=mock_resp):
            result = coupang_uploader.upload_product(prepared)
        assert result['success'] is True
        assert result['product_id'] == '99999'

    def test_upload_product_api_error(self, coupang_uploader):
        prepared = coupang_uploader.prepare_product(SAMPLE_COLLECTED)
        with patch.object(coupang_uploader, '_api_request', return_value={'error': 'bad request'}):
            result = coupang_uploader.upload_product(prepared)
        assert result['success'] is False

    def test_upload_product_data_is_number(self, coupang_uploader):
        """쿠팡은 data를 sellerProductId 숫자로 직접 반환 — 크래시 없이 매핑."""
        prepared = coupang_uploader.prepare_product(SAMPLE_COLLECTED)
        with patch.object(coupang_uploader, '_api_request',
                          return_value={'code': 'SUCCESS', 'data': 12345678}):
            result = coupang_uploader.upload_product(prepared)
        assert result['success'] is True
        assert result['product_id'] == '12345678'

    def test_upload_product_data_null_rejected(self, coupang_uploader):
        """data=null + 비성공 코드 → 가짜 성공이 아니라 정직한 실패 (NoneType 크래시 금지)."""
        prepared = coupang_uploader.prepare_product(SAMPLE_COLLECTED)
        with patch.object(coupang_uploader, '_api_request',
                          return_value={'code': 'ERROR', 'message': '카테고리 오류', 'data': None}):
            result = coupang_uploader.upload_product(prepared)
        assert result['success'] is False
        assert '카테고리 오류' in result['error']

    def test_get_categories_data_null(self, coupang_uploader):
        """get_categories도 data=null 시 빈 리스트 (크래시 금지)."""
        with patch.object(coupang_uploader, '_api_request', return_value={'code': 'SUCCESS', 'data': None}):
            assert coupang_uploader.get_categories() == []

    def test_update_product(self, coupang_uploader):
        with patch.object(coupang_uploader, '_api_request', return_value={}):
            result = coupang_uploader.update_product('12345', {'salePrice': 9000})
        assert result['success'] is True

    def test_delete_product(self, coupang_uploader):
        with patch.object(coupang_uploader, '_api_request', return_value={}):
            result = coupang_uploader.delete_product('12345')
        assert result is True

    def test_get_categories(self, coupang_uploader):
        with patch.object(coupang_uploader, '_api_request', return_value={'data': [{'id': '1'}]}):
            cats = coupang_uploader.get_categories()
        assert cats == [{'id': '1'}]

    def test_upload_blocked_when_shipping_config_missing(self, monkeypatch):
        """출고지/반품지 미설정 시 가짜 성공이 아니라 정직한 실패 + 누락 env 안내."""
        monkeypatch.setenv('COUPANG_ACCESS_KEY', 'ak')
        monkeypatch.setenv('COUPANG_SECRET_KEY', 'sk')
        monkeypatch.setenv('COUPANG_VENDOR_ID', 'vid')
        for env in (
            'COUPANG_VENDOR_USER_ID', 'COUPANG_RETURN_CENTER_CODE',
            'COUPANG_OUTBOUND_SHIPPING_PLACE_CODE', 'COUPANG_RETURN_ZIP_CODE',
            'COUPANG_RETURN_ADDRESS', 'COUPANG_RETURN_CHARGE_NAME',
            'COUPANG_COMPANY_CONTACT_NUMBER',
        ):
            monkeypatch.delenv(env, raising=False)
        from src.uploaders.coupang_uploader import CoupangUploader
        u = CoupangUploader()
        # API를 절대 호출하지 않아야 함(미리 차단)
        with patch.object(u, '_api_request', side_effect=AssertionError('호출 금지')):
            result = u.upload_product(u.prepare_product(SAMPLE_COLLECTED))
        assert result['success'] is False
        assert 'COUPANG_RETURN_CENTER_CODE' in result['error']
        assert 'COUPANG_VENDOR_USER_ID' in result['error']

    def test_payload_has_required_option_and_return_fields(self, coupang_uploader):
        """페이로드에 옵션·반품지 필수 필드가 null 없이 모두 채워진다."""
        prepared = coupang_uploader.prepare_product(SAMPLE_COLLECTED)
        payload = coupang_uploader._build_product_payload(prepared)
        item = payload['items'][0]
        # 옵션 레벨 필수값 (등록 거부 원인이었던 필드들)
        for key in (
            'maximumBuyForPersonPeriod', 'taxType', 'unitCount', 'adultOnly',
            'overseasPurchased', 'notices', 'contents', 'images',
        ):
            assert item.get(key) not in (None, ''), f'item.{key} 누락'
        assert item['taxType'] == 'TAX'
        assert item['adultOnly'] == 'EVERYONE'
        assert item['notices'], '고시정보 비어있음'
        assert item['contents'], '컨텐츠 비어있음'
        # 대표 이미지 타입은 REPRESENTATION
        assert item['images'][0]['imageType'] == 'REPRESENTATION'
        assert all(img['imageType'] != 'PRODUCT' for img in item['images'])
        # 상품 레벨 필수값 (묶음/도서산간/반품지/출고지/vendorUserId)
        for key in (
            'unionDeliveryType', 'remoteAreaDeliverable', 'returnCenterCode',
            'returnChargeName', 'companyContactNumber', 'returnZipCode',
            'returnAddress', 'returnAddressDetail', 'returnCharge',
            'outboundShippingPlaceCode', 'vendorUserId',
        ):
            assert payload.get(key) not in (None, ''), f'root.{key} 누락'
        assert payload['returnCenterCode'] == '1000274592'
        assert payload['vendorUserId'] == 'wing_user'


# ===========================================================================
# Part III: NaverSmartStoreUploader
# ===========================================================================

class TestNaverUploaderInit:
    def test_init_reads_env(self, monkeypatch):
        monkeypatch.setenv('NAVER_CLIENT_ID', 'ncid')
        monkeypatch.setenv('NAVER_CLIENT_SECRET', 'ncs')
        from src.uploaders.naver_uploader import NaverSmartStoreUploader
        u = NaverSmartStoreUploader()
        assert u.client_id == 'ncid'
        assert u.client_secret == 'ncs'

    def test_init_logs_warning_on_missing_keys(self, monkeypatch, caplog):
        monkeypatch.delenv('NAVER_CLIENT_ID', raising=False)
        monkeypatch.delenv('NAVER_CLIENT_SECRET', raising=False)
        import logging
        from src.uploaders.naver_uploader import NaverSmartStoreUploader
        with caplog.at_level(logging.WARNING):
            NaverSmartStoreUploader()
        assert any('NAVER' in r.message for r in caplog.records)

    def test_token_fields_initialized(self, naver_uploader):
        assert naver_uploader._access_token is None
        assert naver_uploader._token_expires == 0


class TestNaverPrepareProduct:
    def test_title_prefix(self, naver_uploader):
        result = naver_uploader.prepare_product(SAMPLE_COLLECTED)
        assert result['title'].startswith('[해외직구]')

    def test_price_round_up_10(self, naver_uploader):
        collected = dict(SAMPLE_COLLECTED, sell_price_krw=12005)
        result = naver_uploader.prepare_product(collected)
        # 12005 → 12010 (10원 단위 올림)
        assert result['price'] % 10 == 0
        assert result['price'] >= 12005

    def test_category_mapped(self, naver_uploader):
        collected = dict(SAMPLE_COLLECTED, category_code='BTY')
        result = naver_uploader.prepare_product(collected)
        assert result['category_id'] == '50000002'

    def test_delivery_days(self, naver_uploader):
        result = naver_uploader.prepare_product(SAMPLE_COLLECTED)
        assert result['delivery_days'] == '7-14'

    def test_empty_product_returns_empty(self, naver_uploader):
        result = naver_uploader.prepare_product({})
        assert result == {}


class TestNaverGetAccessToken:
    def test_token_request_success(self, naver_uploader):
        # 네이버 시크릿은 **bcrypt salt**($2a$…) — 평문이면 서명이 안 돼 토큰 요청 자체가 안 나간다.
        import bcrypt
        naver_uploader.client_secret = bcrypt.gensalt(rounds=4).decode()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'access_token': 'tok123', 'expires_in': 3600}
        with patch('requests.request', return_value=mock_resp):
            token = naver_uploader._get_access_token()
        assert token == 'tok123'
        assert naver_uploader._access_token == 'tok123'

    def test_token_cached(self, naver_uploader):
        naver_uploader._access_token = 'cached-token'
        naver_uploader._token_expires = 9999999999.0
        with patch('requests.request') as mock_post:
            token = naver_uploader._get_access_token()
        mock_post.assert_not_called()
        assert token == 'cached-token'

    def test_token_request_failure_returns_empty(self, naver_uploader):
        with patch('requests.request', side_effect=Exception('network error')):
            token = naver_uploader._get_access_token()
        assert token == ''


class TestNaverUploadProduct:
    def test_upload_product_success(self, naver_uploader):
        prepared = naver_uploader.prepare_product(SAMPLE_COLLECTED)
        # 이미지는 **네이버 CDN 업로드**를 거친다(P5 정본) — 이 테스트는 등록 페이로드 관심사라 목킹.
        with patch.object(naver_uploader, 'upload_images',
                          return_value={'ok': True, 'urls': ['https://shop-phinf.naver.net/a.jpg'],
                                        'skipped': [], 'reason': ''}), \
             patch.object(naver_uploader, '_api_request', return_value={'originProductNo': '55555'}):
            result = naver_uploader.upload_product(prepared)
        assert result['success'] is True
        assert result['product_id'] == '55555'

    def test_upload_product_blocked_when_images_fail(self, naver_uploader):
        """이미지 업로드 0장이면 등록 차단(P5 정본 게이트) — 등록 호출조차 안 한다."""
        prepared = naver_uploader.prepare_product(SAMPLE_COLLECTED)
        with patch.object(naver_uploader, 'upload_images',
                          return_value={'ok': False, 'urls': [], 'skipped': [],
                                        'reason': '전부 실패'}), \
             patch.object(naver_uploader, '_api_request') as api:
            result = naver_uploader.upload_product(prepared)
        assert result['success'] is False and result['held'] is True
        api.assert_not_called()

    def test_upload_product_error(self, naver_uploader):
        prepared = naver_uploader.prepare_product(SAMPLE_COLLECTED)
        with patch.object(naver_uploader, 'upload_images',
                          return_value={'ok': True, 'urls': ['https://shop-phinf.naver.net/a.jpg'],
                                        'skipped': [], 'reason': ''}), \
             patch.object(naver_uploader, '_api_request', return_value={'error': 'bad request'}):
            result = naver_uploader.upload_product(prepared)
        assert result['success'] is False

    def test_update_product_success(self, naver_uploader):
        with patch.object(naver_uploader, '_api_request', return_value={}):
            result = naver_uploader.update_product('55555', {'salePrice': 9000})
        assert result['success'] is True

    def test_delete_product_success(self, naver_uploader):
        with patch.object(naver_uploader, '_api_request', return_value={}):
            result = naver_uploader.delete_product('55555')
        assert result is True


# ===========================================================================
# Part IV: UploadManager
# ===========================================================================

class TestUploadManager:
    def test_init(self, upload_manager):
        assert upload_manager is not None

    def test_get_uploader_coupang(self, upload_manager):
        from src.uploaders.coupang_uploader import CoupangUploader
        u = upload_manager._get_uploader('coupang')
        assert isinstance(u, CoupangUploader)

    def test_get_uploader_naver(self, upload_manager):
        from src.uploaders.naver_uploader import NaverSmartStoreUploader
        u = upload_manager._get_uploader('naver')
        assert isinstance(u, NaverSmartStoreUploader)

    def test_get_uploader_invalid_raises(self, upload_manager):
        with pytest.raises(ValueError):
            upload_manager._get_uploader('invalid_market')

    def test_upload_to_market_dry_run(self, upload_manager):
        mock_product = dict(SAMPLE_COLLECTED)
        with patch.object(upload_manager, '_fetch_products_by_sku', return_value={'TAO-DIG-012': mock_product}):
            result = upload_manager.upload_to_market(['TAO-DIG-012'], 'coupang', dry_run=True)
        assert result['total'] == 1
        assert result['success'] == 1
        assert result['failed'] == 0
        assert result['results'][0]['dry_run'] is True

    def test_upload_to_market_product_not_found(self, upload_manager):
        with patch.object(upload_manager, '_fetch_products_by_sku', return_value={}):
            result = upload_manager.upload_to_market(['UNKNOWN-SKU'], 'coupang', dry_run=True)
        assert result['failed'] == 1
        assert result['success'] == 0

    def test_upload_to_market_empty_skus(self, upload_manager):
        result = upload_manager.upload_to_market([], 'coupang')
        assert result['total'] == 0

    def test_upload_to_market_invalid_market(self, upload_manager):
        result = upload_manager.upload_to_market(['TAO-DIG-012'], 'invalid')
        assert result['failed'] == 1

    def test_upload_all_pending_no_pending(self, upload_manager):
        with patch.object(upload_manager, '_get_pending_skus', return_value=[]):
            result = upload_manager.upload_all_pending('coupang')
        assert result['total'] == 0

    def test_upload_all_pending_calls_upload(self, upload_manager):
        with patch.object(upload_manager, '_get_pending_skus', return_value=['SKU-1']):
            with patch.object(upload_manager, 'upload_to_market', return_value={
                'total': 1, 'success': 1, 'failed': 0, 'results': []
            }) as mock_upload:
                upload_manager.upload_all_pending('coupang', dry_run=True)
        mock_upload.assert_called_once_with(['SKU-1'], 'coupang', dry_run=True)

    def test_get_upload_history_empty_on_error(self, upload_manager):
        with patch.object(upload_manager, '_get_upload_worksheet', side_effect=Exception('no sheet')):
            result = upload_manager.get_upload_history()
        assert result == []

    def test_get_upload_history_with_filter(self, upload_manager):
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {'sku': 'A', 'market': 'coupang', 'status': 'success'},
            {'sku': 'B', 'market': 'naver', 'status': 'success'},
        ]
        with patch.object(upload_manager, '_get_upload_worksheet', return_value=mock_ws):
            result = upload_manager.get_upload_history({'market': 'coupang'})
        assert len(result) == 1
        assert result[0]['sku'] == 'A'

    def test_generate_report(self, upload_manager):
        mock_history = [
            {'sku': 'A', 'market': 'coupang', 'status': 'success'},
            {'sku': 'B', 'market': 'coupang', 'status': 'failed'},
            {'sku': 'C', 'market': 'naver', 'status': 'success'},
        ]
        with patch.object(upload_manager, 'get_upload_history', return_value=mock_history):
            report = upload_manager.generate_report()
        assert report['total'] == 3
        assert report['by_market']['coupang'] == 2
        assert report['by_market']['naver'] == 1
        assert report['by_status']['success'] == 2

    def test_generate_report_empty(self, upload_manager):
        with patch.object(upload_manager, 'get_upload_history', return_value=[]):
            report = upload_manager.generate_report()
        assert report['total'] == 0

    def test_sync_prices_dry_run(self, upload_manager):
        mock_history = [{'sku': 'TAO-DIG-012', 'market': 'coupang', 'product_id': '999', 'status': 'success'}]
        mock_product = dict(SAMPLE_COLLECTED)
        with patch.object(upload_manager, 'get_upload_history', return_value=mock_history):
            with patch.object(upload_manager, '_fetch_products_by_sku', return_value={'TAO-DIG-012': mock_product}):
                result = upload_manager.sync_prices('coupang', dry_run=True)
        assert result['total'] == 1
        assert result['success'] == 1


# ===========================================================================
# Part V: Upload CLI
# ===========================================================================

class TestUploadCLI:
    def test_cli_report(self, capsys):
        from src.uploaders.cli import main
        with patch('src.uploaders.upload_manager.UploadManager.generate_report',
                   return_value={'total': 0, 'by_market': {}, 'by_status': {}}):
            main(['--action', 'report'])
        out = capsys.readouterr().out
        assert 'total' in out

    def test_cli_upload_requires_market(self, capsys):
        from src.uploaders.cli import main
        with pytest.raises(SystemExit):
            main(['--action', 'upload', '--skus', 'SKU-1'])

    def test_cli_upload_requires_skus(self, capsys):
        from src.uploaders.cli import main
        with pytest.raises(SystemExit):
            main(['--action', 'upload', '--market', 'coupang'])

    def test_cli_upload_dry_run(self, capsys):
        from src.uploaders.cli import main
        mock_result = {'total': 1, 'success': 1, 'failed': 0, 'results': []}
        with patch('src.uploaders.upload_manager.UploadManager.upload_to_market',
                   return_value=mock_result):
            main(['--market', 'coupang', '--skus', 'TAO-DIG-012', '--dry-run'])
        out = capsys.readouterr().out
        assert 'total' in out

    def test_cli_upload_pending(self, capsys):
        from src.uploaders.cli import main
        mock_result = {'total': 0, 'success': 0, 'failed': 0, 'results': []}
        with patch('src.uploaders.upload_manager.UploadManager.upload_all_pending',
                   return_value=mock_result):
            main(['--market', 'naver', '--action', 'upload-pending', '--dry-run'])
        out = capsys.readouterr().out
        assert 'total' in out

    def test_cli_upload_pending_requires_market(self, capsys):
        from src.uploaders.cli import main
        with pytest.raises(SystemExit):
            main(['--action', 'upload-pending'])

    def test_cli_sync_prices(self, capsys):
        from src.uploaders.cli import main
        mock_result = {'total': 0, 'success': 0, 'failed': 0, 'results': []}
        with patch('src.uploaders.upload_manager.UploadManager.sync_prices',
                   return_value=mock_result):
            main(['--market', 'coupang', '--action', 'sync-prices', '--dry-run'])
        out = capsys.readouterr().out
        assert 'total' in out

    def test_cli_sync_prices_requires_market(self, capsys):
        from src.uploaders.cli import main
        with pytest.raises(SystemExit):
            main(['--action', 'sync-prices'])
