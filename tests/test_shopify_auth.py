"""tests/test_shopify_auth.py — Shopify 인증 강화 테스트"""
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

def _make_hmac(secret: str, data: bytes) -> str:
    digest = hmac.new(secret.encode(), data, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


# ──────────────────────────────────────────────────────────
# verify_webhook tests (shopify_client)
# ──────────────────────────────────────────────────────────

class TestVerifyWebhook:
    def setup_method(self):
        import src.vendors.shopify_client as mod
        self.mod = mod

    def test_verify_webhook_valid(self):
        secret = 'test_secret'
        data = b'{"order_id": 123}'
        header = _make_hmac(secret, data)
        with patch.object(self.mod, 'CLIENT_SECRET', secret):
            assert self.mod.verify_webhook(data, header) is True

    def test_verify_webhook_invalid(self):
        secret = 'test_secret'
        data = b'{"order_id": 123}'
        with patch.object(self.mod, 'CLIENT_SECRET', secret):
            assert self.mod.verify_webhook(data, 'bad_hmac_value') is False

    def test_verify_webhook_no_secret(self):
        """CLIENT_SECRET 미설정 시 graceful degradation (True 반환)."""
        with patch.object(self.mod, 'CLIENT_SECRET', None):
            assert self.mod.verify_webhook(b'any data', 'any_header') is True


# ──────────────────────────────────────────────────────────
# _request_with_retry tests (shopify_client)
# ──────────────────────────────────────────────────────────

class TestRequestWithRetry:
    def setup_method(self):
        import src.vendors.shopify_client as mod
        self.mod = mod

    def test_request_with_retry_429(self):
        """429 응답 시 재시도 로직 동작 확인."""
        rate_limit_resp = MagicMock()
        rate_limit_resp.status_code = 429
        rate_limit_resp.headers = {'Retry-After': '0.01'}

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.raise_for_status = MagicMock()

        with patch('requests.request', side_effect=[rate_limit_resp, ok_resp]):
            with patch('time.sleep'):
                r = self.mod._request_with_retry('GET', 'http://example.com')
                assert r.status_code == 200

    def test_request_with_retry_connection_error(self):
        """연결 에러 시 재시도 후 최종 실패."""
        with patch('requests.request', side_effect=requests.exceptions.ConnectionError("conn err")):
            with patch('time.sleep'):
                with pytest.raises(requests.exceptions.ConnectionError):
                    self.mod._request_with_retry('GET', 'http://example.com', max_retries=2)


# ──────────────────────────────────────────────────────────
# graphql_query tests (shopify_client)
# ──────────────────────────────────────────────────────────

class TestGraphqlQuery:
    def setup_method(self):
        import src.vendors.shopify_client as mod
        self.mod = mod

    def test_graphql_query_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {'data': {'shop': {'name': 'Test Store'}}}

        with patch.object(self.mod, '_request_with_retry', return_value=mock_resp):
            result = self.mod.graphql_query('{ shop { name } }')
            assert result == {'shop': {'name': 'Test Store'}}

    def test_graphql_query_errors(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {'errors': [{'message': 'Field not found'}]}

        with patch.object(self.mod, '_request_with_retry', return_value=mock_resp):
            with pytest.raises(RuntimeError, match='Shopify GraphQL error'):
                self.mod.graphql_query('{ invalid }')


# ──────────────────────────────────────────────────────────
# upsert_product backward compat test (shopify_client)
# ──────────────────────────────────────────────────────────

class TestUpsertProductBackwardCompat:
    def setup_method(self):
        import src.vendors.shopify_client as mod
        self.mod = mod

    def test_upsert_product_backward_compat_create(self):
        """upsert_product()가 신규 상품을 생성하는 경우 (기존 시그니처 유지)."""
        prod = {
            'title': 'Test Product',
            'variants': [{'sku': 'TEST-001', 'price': '10.00'}],
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = {'product': {'id': 999, **prod}}

        with patch.object(self.mod, '_find_by_sku', return_value=None):
            with patch.object(self.mod, '_request_with_retry', return_value=mock_resp):
                result = self.mod.upsert_product(prod)
                assert result['id'] == 999

    def test_upsert_product_backward_compat_update(self):
        """upsert_product()가 기존 상품을 갱신하는 경우."""
        prod = {
            'title': 'Test Product',
            'variants': [{'sku': 'TEST-001', 'price': '15.00'}],
        }
        existing = {'id': 42, 'title': 'Old Title'}

        mock_resp = MagicMock()
        mock_resp.json.return_value = {'product': {'id': 42, **prod}}

        with patch.object(self.mod, '_find_by_sku', return_value=existing):
            with patch.object(self.mod, '_request_with_retry', return_value=mock_resp):
                result = self.mod.upsert_product(prod)
                assert result['id'] == 42


# ──────────────────────────────────────────────────────────
# validate_access_token tests (shopify_oauth)
# ──────────────────────────────────────────────────────────

class TestValidateAccessToken:
    def setup_method(self):
        import src.auth.shopify_oauth as mod
        self.mod = mod

    def test_validate_access_token_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'shop': {'name': 'My Store'}}

        with patch.object(self.mod, 'SHOP', 'test.myshopify.com'):
            with patch.object(self.mod, 'TOKEN', 'shpat_test'):
                with patch('requests.get', return_value=mock_resp):
                    assert self.mod.validate_access_token() is True

    def test_validate_access_token_expired(self):
        """401 응답 시 False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch.object(self.mod, 'SHOP', 'test.myshopify.com'):
            with patch.object(self.mod, 'TOKEN', 'expired_token'):
                with patch('requests.get', return_value=mock_resp):
                    assert self.mod.validate_access_token() is False

    def test_validate_access_token_no_env(self):
        """환경변수 없을 때 False."""
        with patch.object(self.mod, 'SHOP', None):
            with patch.object(self.mod, 'TOKEN', None):
                assert self.mod.validate_access_token() is False


# ──────────────────────────────────────────────────────────
# get_scopes tests (shopify_oauth)
# ──────────────────────────────────────────────────────────

class TestGetScopes:
    def setup_method(self):
        import src.auth.shopify_oauth as mod
        self.mod = mod

    def test_get_scopes_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            'access_scopes': [
                {'handle': 'read_products'},
                {'handle': 'write_products'},
            ]
        }

        with patch.object(self.mod, 'SHOP', 'test.myshopify.com'):
            with patch.object(self.mod, 'TOKEN', 'shpat_test'):
                with patch('requests.get', return_value=mock_resp):
                    scopes = self.mod.get_scopes()
                    assert 'read_products' in scopes
                    assert 'write_products' in scopes


# ──────────────────────────────────────────────────────────
# secret_check tests
# ──────────────────────────────────────────────────────────

class TestSecretCheck:
    def setup_method(self):
        import src.utils.secret_check as mod
        self.mod = mod

    def test_secret_check_all_set(self):
        env = {
            'GOOGLE_SERVICE_JSON_B64': 'val',
            'GOOGLE_SHEET_ID': 'val',
            'SHOPIFY_SHOP': 'val',
            'SHOPIFY_ACCESS_TOKEN': 'val',
            'SHOPIFY_CLIENT_SECRET': 'val',
            'WOO_BASE_URL': 'val',
            'WOO_CK': 'val',
            'WOO_CS': 'val',
        }
        with patch.dict(os.environ, env, clear=False):
            results = self.mod.check_secrets()
            for grp in ('core', 'shopify', 'woocommerce'):
                assert results[grp]['missing'] == []

    def test_secret_check_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            results = self.mod.check_secrets(group='shopify')
            assert set(results['shopify']['missing']) == {
                'SHOPIFY_SHOP', 'SHOPIFY_ACCESS_TOKEN', 'SHOPIFY_CLIENT_SECRET'
            }

    def test_check_all_returns_false_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert self.mod.check_all() is False
