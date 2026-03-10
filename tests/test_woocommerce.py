"""tests/test_woocommerce.py — WooCommerce 클라이언트 단위 테스트"""
import base64
import hashlib
import hmac
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────

def _make_woo_hmac(secret: str, data: bytes) -> str:
    digest = hmac.new(secret.encode(), data, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _ok_response(json_data=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data or {}
    return resp


# ──────────────────────────────────────────────────────────
# _request_with_retry tests
# ──────────────────────────────────────────────────────────

class TestRequestWithRetry:
    def setup_method(self):
        import src.vendors.woocommerce_client as mod
        self.mod = mod

    def test_request_with_retry_success(self):
        """정상 요청 — 첫 번째 시도에 성공."""
        ok = _ok_response({'id': 1})
        with patch('requests.request', return_value=ok) as mock_req:
            r = self.mod._request_with_retry('GET', 'http://example.com/wp-json/wc/v3/products')
            assert r.status_code == 200
            assert mock_req.call_count == 1

    def test_request_with_retry_429(self):
        """429 응답 시 Retry-After 대기 후 재시도."""
        rate_limit = MagicMock()
        rate_limit.status_code = 429
        rate_limit.headers = {'Retry-After': '0.01'}

        ok = _ok_response({'id': 1})

        with patch('requests.request', side_effect=[rate_limit, ok]):
            with patch('time.sleep') as mock_sleep:
                r = self.mod._request_with_retry('GET', 'http://example.com')
                assert r.status_code == 200
                mock_sleep.assert_called_once_with(0.01)

    def test_request_with_retry_500(self):
        """5xx 에러 시 지수 백오프 후 재시도."""
        server_err = MagicMock()
        server_err.status_code = 500
        server_err.headers = {}

        ok = _ok_response()

        with patch('requests.request', side_effect=[server_err, ok]):
            with patch('time.sleep') as mock_sleep:
                r = self.mod._request_with_retry('GET', 'http://example.com')
                assert r.status_code == 200
                mock_sleep.assert_called_once_with(1)  # 2^0 = 1

    def test_request_with_retry_connection_error(self):
        """연결 에러 시 재시도 후 최종 실패."""
        with patch('requests.request', side_effect=requests.exceptions.ConnectionError("conn err")):
            with patch('time.sleep'):
                with pytest.raises(requests.exceptions.ConnectionError):
                    self.mod._request_with_retry('GET', 'http://example.com', max_retries=2)

    def test_request_with_retry_max_retries_exceeded(self):
        """모든 재시도 소진 후 RuntimeError."""
        server_err = MagicMock()
        server_err.status_code = 503
        server_err.headers = {}

        with patch('requests.request', return_value=server_err):
            with patch('time.sleep'):
                with pytest.raises(RuntimeError, match="Max retries exceeded"):
                    self.mod._request_with_retry('GET', 'http://example.com', max_retries=2)

    def test_request_merges_auth_params(self):
        """auth params와 추가 params가 함께 전달된다."""
        ok = _ok_response([])
        with patch('requests.request', return_value=ok) as mock_req:
            with patch.object(self.mod, 'CK', 'ck_test'):
                with patch.object(self.mod, 'CS', 'cs_test'):
                    self.mod._request_with_retry('GET', 'http://example.com', params={'sku': 'ABC'})
                    called_params = mock_req.call_args[1]['params']
                    assert called_params['consumer_key'] == 'ck_test'
                    assert called_params['consumer_secret'] == 'cs_test'
                    assert called_params['sku'] == 'ABC'


# ──────────────────────────────────────────────────────────
# _prepare_images tests
# ──────────────────────────────────────────────────────────

class TestPrepareImages:
    def setup_method(self):
        import src.vendors.woocommerce_client as mod
        self.mod = mod

    def test_prepare_images(self):
        """콤마 구분 URL → WooCommerce images 배열."""
        result = self.mod._prepare_images('https://example.com/a.jpg,https://example.com/b.jpg')
        assert len(result) == 2
        assert result[0] == {'src': 'https://example.com/a.jpg', 'position': 0}
        assert result[1] == {'src': 'https://example.com/b.jpg', 'position': 1}

    def test_prepare_images_empty(self):
        """빈 문자열 → 빈 리스트."""
        assert self.mod._prepare_images('') == []
        assert self.mod._prepare_images(None) == []

    def test_prepare_images_whitespace(self):
        """공백 포함 URL 트리밍."""
        result = self.mod._prepare_images('  https://example.com/a.jpg  ,  https://example.com/b.jpg  ')
        assert result[0]['src'] == 'https://example.com/a.jpg'
        assert result[1]['src'] == 'https://example.com/b.jpg'

    def test_prepare_images_single(self):
        """단일 URL."""
        result = self.mod._prepare_images('https://example.com/only.jpg')
        assert len(result) == 1
        assert result[0] == {'src': 'https://example.com/only.jpg', 'position': 0}


# ──────────────────────────────────────────────────────────
# _prepare_stock tests
# ──────────────────────────────────────────────────────────

class TestPrepareStock:
    def setup_method(self):
        import src.vendors.woocommerce_client as mod
        self.mod = mod

    def test_prepare_stock_instock(self):
        """재고 있음 — instock 상태."""
        result = self.mod._prepare_stock(5)
        assert result['manage_stock'] is True
        assert result['stock_quantity'] == 5
        assert result['stock_status'] == 'instock'

    def test_prepare_stock_outofstock(self):
        """재고 0 — outofstock 상태."""
        result = self.mod._prepare_stock(0)
        assert result['stock_quantity'] == 0
        assert result['stock_status'] == 'outofstock'

    def test_prepare_stock_none(self):
        """None → 재고 0, outofstock."""
        result = self.mod._prepare_stock(None)
        assert result['stock_quantity'] == 0
        assert result['stock_status'] == 'outofstock'

    def test_prepare_stock_manage_false(self):
        """manage=False 시 manage_stock False."""
        result = self.mod._prepare_stock(10, manage=False)
        assert result['manage_stock'] is False


# ──────────────────────────────────────────────────────────
# _generate_description tests
# ──────────────────────────────────────────────────────────

class TestGenerateDescription:
    def setup_method(self):
        import src.vendors.woocommerce_client as mod
        self.mod = mod

    def test_generate_description_porter(self):
        """PORTER 벤더 HTML 설명 — 젠마켓 배송 안내 포함."""
        row = {
            'vendor': 'PORTER',
            'title_ko': '탱커 브리프케이스',
            'brand': 'PORTER',
            'source_country': 'JP',
            'category': 'bag',
        }
        html = self.mod._generate_description(row)
        assert '탱커 브리프케이스' in html
        assert 'PORTER' in html
        assert '일본' in html
        assert '젠마켓' in html
        assert '7-14일' in html
        assert '관부가세' in html

    def test_generate_description_memo(self):
        """MEMO_PARIS 벤더 HTML 설명 — 프랑스 직구 배송 안내 포함."""
        row = {
            'vendor': 'MEMO_PARIS',
            'title_ko': '아프리칸 레더',
            'brand': 'MEMO_PARIS',
            'source_country': 'FR',
            'category': 'perfume',
        }
        html = self.mod._generate_description(row)
        assert '아프리칸 레더' in html
        assert '프랑스' in html
        assert '10-18일' in html
        assert '관부가세' in html


# ──────────────────────────────────────────────────────────
# prepare_product_data tests
# ──────────────────────────────────────────────────────────

PORTER_CATALOG_ROW = {
    'vendor': 'PORTER',
    'sku': 'PTR-TNK-100000',
    'title_ko': '탱커 2WAY 브리프케이스',
    'title_en': 'Tanker 2WAY Briefcase',
    'brand': 'PORTER',
    'category': 'bag',
    'source_country': 'JP',
    'buy_price': 30800.0,
    'buy_currency': 'JPY',
    'stock': 3,
    'images': 'https://example.com/img1.jpg,https://example.com/img2.jpg',
    'tags': '가방,비즈니스',
}

MEMO_CATALOG_ROW = {
    'vendor': 'MEMO_PARIS',
    'sku': 'MMP-EDP-001',
    'title_ko': '아프리칸 레더 오 드 퍼퓸',
    'title_en': 'African Leather Eau de Parfum',
    'brand': 'MEMO_PARIS',
    'category': 'perfume',
    'source_country': 'FR',
    'buy_price': 250.0,
    'buy_currency': 'EUR',
    'stock': 0,
    'images': 'https://example.com/memo1.jpg',
    'tags': '향수,EDP',
}


class TestPrepareProductData:
    def setup_method(self):
        import src.vendors.woocommerce_client as mod
        self.mod = mod

    def test_prepare_product_data_porter(self):
        """PORTER 상품 변환 — 기본 필드 확인."""
        mock_cat_id = 10
        mock_tag_id = 20

        with patch.object(self.mod, 'get_or_create_category', return_value=mock_cat_id):
            with patch.object(self.mod, 'get_or_create_tag', return_value=mock_tag_id):
                result = self.mod.prepare_product_data(PORTER_CATALOG_ROW, 45000.0)

        assert result['name'] == '탱커 2WAY 브리프케이스'
        assert result['sku'] == 'PTR-TNK-100000'
        assert result['regular_price'] == '45000'
        assert result['manage_stock'] is True
        assert result['stock_quantity'] == 3
        assert result['stock_status'] == 'instock'
        assert result['shipping_class'] == 'overseas'
        assert len(result['images']) == 2
        assert result['categories'] == [{'id': mock_cat_id}]
        assert len(result['tags']) == 2

    def test_prepare_product_data_memo(self):
        """MEMO_PARIS 상품 변환 — 재고 없음."""
        with patch.object(self.mod, 'get_or_create_category', return_value=5):
            with patch.object(self.mod, 'get_or_create_tag', return_value=15):
                result = self.mod.prepare_product_data(MEMO_CATALOG_ROW, 380000.0)

        assert result['name'] == '아프리칸 레더 오 드 퍼퓸'
        assert result['regular_price'] == '380000'
        assert result['stock_status'] == 'outofstock'
        assert result['stock_quantity'] == 0

    def test_prepare_product_data_uses_title_en_fallback(self):
        """title_ko 없을 때 title_en 사용."""
        row = {**PORTER_CATALOG_ROW, 'title_ko': ''}
        with patch.object(self.mod, 'get_or_create_category', return_value=1):
            with patch.object(self.mod, 'get_or_create_tag', return_value=1):
                result = self.mod.prepare_product_data(row, 45000.0)
        assert result['name'] == 'Tanker 2WAY Briefcase'

    def test_prepare_product_data_category_failure_graceful(self):
        """카테고리 조회 실패 시 상품 데이터에서 categories 제외 (크래시 없음)."""
        with patch.object(self.mod, 'get_or_create_category', side_effect=RuntimeError("API error")):
            with patch.object(self.mod, 'get_or_create_tag', return_value=1):
                result = self.mod.prepare_product_data(PORTER_CATALOG_ROW, 45000.0)
        assert 'categories' not in result

    def test_prepare_product_data_meta_data(self):
        """meta_data 필드 확인."""
        with patch.object(self.mod, 'get_or_create_category', return_value=1):
            with patch.object(self.mod, 'get_or_create_tag', return_value=1):
                result = self.mod.prepare_product_data(PORTER_CATALOG_ROW, 45000.0)
        keys = [m['key'] for m in result['meta_data']]
        assert 'source_country' in keys
        assert 'original_price' in keys
        assert 'vendor' in keys


# ──────────────────────────────────────────────────────────
# verify_woo_webhook tests
# ──────────────────────────────────────────────────────────

class TestVerifyWooWebhook:
    def setup_method(self):
        import src.vendors.woocommerce_client as mod
        self.mod = mod

    def test_verify_woo_webhook_valid(self):
        """유효한 서명 — True 반환."""
        secret = 'woo_test_secret'
        payload = b'{"order_id": 456}'
        signature = _make_woo_hmac(secret, payload)
        with patch.object(self.mod, 'WOO_WEBHOOK_SECRET', secret):
            assert self.mod.verify_woo_webhook(payload, signature) is True

    def test_verify_woo_webhook_invalid(self):
        """잘못된 서명 — False 반환."""
        secret = 'woo_test_secret'
        payload = b'{"order_id": 456}'
        with patch.object(self.mod, 'WOO_WEBHOOK_SECRET', secret):
            assert self.mod.verify_woo_webhook(payload, 'invalid_signature==') is False

    def test_verify_woo_webhook_no_secret(self):
        """WOO_WEBHOOK_SECRET 미설정 시 True 반환 (graceful degradation)."""
        with patch.object(self.mod, 'WOO_WEBHOOK_SECRET', ''):
            assert self.mod.verify_woo_webhook(b'any data', 'any_header') is True


# ──────────────────────────────────────────────────────────
# upsert_product backward compat tests
# ──────────────────────────────────────────────────────────

class TestUpsertProductBackwardCompat:
    def setup_method(self):
        import src.vendors.woocommerce_client as mod
        self.mod = mod

    def test_upsert_product_backward_compat_create(self):
        """신규 상품 생성 — 기존 시그니처 유지."""
        prod = {'name': 'Test', 'sku': 'TST-001', 'regular_price': '10000'}
        mock_resp = _ok_response({'id': 99, **prod})

        with patch.object(self.mod, '_find_by_sku', return_value=None):
            with patch.object(self.mod, '_request_with_retry', return_value=mock_resp):
                result = self.mod.upsert_product(prod)
                assert result['id'] == 99

    def test_upsert_product_backward_compat_update(self):
        """기존 상품 갱신 — 기존 시그니처 유지."""
        prod = {'name': 'Test Updated', 'sku': 'TST-001', 'regular_price': '12000'}
        existing = {'id': 42}
        mock_resp = _ok_response({'id': 42, **prod})

        with patch.object(self.mod, '_find_by_sku', return_value=existing):
            with patch.object(self.mod, '_request_with_retry', return_value=mock_resp):
                result = self.mod.upsert_product(prod)
                assert result['id'] == 42


# ──────────────────────────────────────────────────────────
# upsert_batch tests
# ──────────────────────────────────────────────────────────

class TestUpsertBatch:
    def setup_method(self):
        import src.vendors.woocommerce_client as mod
        self.mod = mod

    def test_upsert_batch_mixed(self):
        """배치 upsert — 신규/갱신 혼합."""
        products = [
            {'sku': 'NEW-001', 'name': 'New Product'},
            {'sku': 'UPD-001', 'name': 'Updated Product'},
        ]

        def mock_find_by_sku(sku):
            if sku == 'UPD-001':
                return {'id': 55}
            return None

        batch_resp = _ok_response({'create': [{'id': 100}], 'update': [{'id': 55}]})

        with patch.object(self.mod, '_find_by_sku', side_effect=mock_find_by_sku):
            with patch.object(self.mod, '_request_with_retry', return_value=batch_resp):
                result = self.mod.upsert_batch(products)
                assert result['created'] == 1
                assert result['updated'] == 1
                assert result['errors'] == []

    def test_upsert_batch_error_handling(self):
        """배치 실패 시 errors 리스트에 추가."""
        products = [{'sku': 'ERR-001', 'name': 'Error Product'}]

        with patch.object(self.mod, '_find_by_sku', return_value=None):
            with patch.object(self.mod, '_request_with_retry', side_effect=RuntimeError("API failure")):
                result = self.mod.upsert_batch(products)
                assert len(result['errors']) == 1
                assert 'API failure' in result['errors'][0]

    def test_upsert_batch_empty(self):
        """빈 리스트 처리."""
        result = self.mod.upsert_batch([])
        assert result == {'created': 0, 'updated': 0, 'errors': []}


# ──────────────────────────────────────────────────────────
# get_or_create_category tests
# ──────────────────────────────────────────────────────────

class TestGetOrCreateCategory:
    def setup_method(self):
        import src.vendors.woocommerce_client as mod
        self.mod = mod

    def test_get_or_create_category_existing(self):
        """기존 카테고리 slug 조회 — ID 반환."""
        existing_resp = _ok_response([{'id': 7, 'slug': 'bag', 'name': '가방'}])
        with patch.object(self.mod, '_request_with_retry', return_value=existing_resp):
            with patch.object(self.mod, 'BASE', 'https://example.com'):
                cat_id = self.mod.get_or_create_category('bag')
                assert cat_id == 7

    def test_get_or_create_category_new(self):
        """카테고리 없으면 생성 후 ID 반환."""
        empty_resp = _ok_response([])
        create_resp = _ok_response({'id': 8, 'slug': 'bag', 'name': '가방'})

        with patch.object(self.mod, '_request_with_retry', side_effect=[empty_resp, create_resp]):
            with patch.object(self.mod, 'BASE', 'https://example.com'):
                cat_id = self.mod.get_or_create_category('bag')
                assert cat_id == 8

    def test_get_or_create_category_unknown_slug(self):
        """알 수 없는 slug → slug 그대로 이름으로 사용."""
        empty_resp = _ok_response([])
        create_resp = _ok_response({'id': 99, 'slug': 'mystery', 'name': 'mystery'})

        with patch.object(self.mod, '_request_with_retry', side_effect=[empty_resp, create_resp]):
            with patch.object(self.mod, 'BASE', 'https://example.com'):
                cat_id = self.mod.get_or_create_category('mystery')
                assert cat_id == 99


# ──────────────────────────────────────────────────────────
# get_or_create_tag tests
# ──────────────────────────────────────────────────────────

class TestGetOrCreateTag:
    def setup_method(self):
        import src.vendors.woocommerce_client as mod
        self.mod = mod

    def test_get_or_create_tag_existing(self):
        """기존 태그 이름 조회 — ID 반환."""
        tags_resp = _ok_response([{'id': 3, 'name': '가방'}])
        with patch.object(self.mod, '_request_with_retry', return_value=tags_resp):
            with patch.object(self.mod, 'BASE', 'https://example.com'):
                tag_id = self.mod.get_or_create_tag('가방')
                assert tag_id == 3

    def test_get_or_create_tag_case_insensitive(self):
        """태그 이름 대소문자 무관 비교."""
        tags_resp = _ok_response([{'id': 4, 'name': 'EDP'}])
        with patch.object(self.mod, '_request_with_retry', return_value=tags_resp):
            with patch.object(self.mod, 'BASE', 'https://example.com'):
                tag_id = self.mod.get_or_create_tag('edp')
                assert tag_id == 4

    def test_get_or_create_tag_new(self):
        """태그 없으면 생성 후 ID 반환."""
        search_resp = _ok_response([])
        create_resp = _ok_response({'id': 5, 'name': 'NewTag'})

        with patch.object(self.mod, '_request_with_retry', side_effect=[search_resp, create_resp]):
            with patch.object(self.mod, 'BASE', 'https://example.com'):
                tag_id = self.mod.get_or_create_tag('NewTag')
                assert tag_id == 5
