"""tests/test_auth.py — Tests for JWT handler, OAuth provider, and auth API blueprint."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# TestJWTHandler
# ──────────────────────────────────────────────────────────

class TestJWTHandler:

    @pytest.fixture
    def handler(self):
        from src.auth.jwt_handler import JWTHandler
        return JWTHandler(secret_key='test-secret-key')

    def test_create_access_token_returns_string(self, handler):
        token = handler.create_access_token({'sub': 'user1'})
        assert isinstance(token, str)
        assert len(token.split('.')) == 3

    def test_decode_token_roundtrip(self, handler):
        payload = {'sub': 'user42', 'role': 'admin'}
        token = handler.create_access_token(payload)
        decoded = handler.decode_token(token)
        assert decoded['sub'] == 'user42'
        assert decoded['role'] == 'admin'

    def test_expired_token_raises_value_error(self, handler):
        from unittest.mock import patch
        token = handler.create_access_token({'sub': 'x'}, expires_in_minutes=15)
        # Simulate time advancing past expiry
        with patch('src.auth.jwt_handler.time') as mock_time:
            mock_time.time.return_value = time.time() + 1000
            with pytest.raises(ValueError, match="expired"):
                handler.decode_token(token)

    def test_invalid_token_raises_value_error(self, handler):
        with pytest.raises(ValueError):
            handler.decode_token("not.a.valid.token")

    def test_invalid_signature_raises_value_error(self, handler):
        token = handler.create_access_token({'sub': 'user1'})
        parts = token.split('.')
        # tamper with payload
        tampered = parts[0] + '.' + parts[1] + 'X' + '.' + parts[2]
        with pytest.raises(ValueError):
            handler.decode_token(tampered)

    def test_is_token_expired_false_for_fresh_token(self, handler):
        token = handler.create_access_token({'sub': 'user1'}, expires_in_minutes=15)
        assert handler.is_token_expired(token) is False

    def test_is_token_expired_true_for_expired_token(self, handler):
        from unittest.mock import patch
        token = handler.create_access_token({'sub': 'user1'}, expires_in_minutes=15)
        with patch('src.auth.jwt_handler.time') as mock_time:
            mock_time.time.return_value = time.time() + 1000
            assert handler.is_token_expired(token) is True

    def test_is_token_expired_true_for_garbage(self, handler):
        assert handler.is_token_expired('garbage') is True


# ──────────────────────────────────────────────────────────
# TestOAuthProvider
# ──────────────────────────────────────────────────────────

class TestOAuthProvider:

    def test_get_authorization_url_google(self):
        from src.auth.oauth_provider import OAuthProvider
        provider = OAuthProvider('google')
        url = provider.get_authorization_url('https://example.com/callback', state='abc123')
        assert url.startswith('https://accounts.google.com/o/oauth2/auth')
        assert 'redirect_uri=' in url
        assert 'state=abc123' in url

    def test_get_authorization_url_kakao(self):
        from src.auth.oauth_provider import OAuthProvider
        provider = OAuthProvider('kakao')
        url = provider.get_authorization_url('https://example.com/callback')
        assert url.startswith('https://kauth.kakao.com/oauth/authorize')
        assert 'redirect_uri=' in url

    def test_map_profile_google(self):
        from src.auth.oauth_provider import OAuthProvider
        provider = OAuthProvider('google')
        raw = {
            'sub': 'g123',
            'email': 'test@gmail.com',
            'name': 'Google User',
            'picture': 'https://pic.url/avatar.jpg',
        }
        mapped = provider.map_profile(raw, 'google')
        assert mapped['id'] == 'g123'
        assert mapped['email'] == 'test@gmail.com'
        assert mapped['name'] == 'Google User'
        assert mapped['provider'] == 'google'
        assert mapped['avatar_url'] == 'https://pic.url/avatar.jpg'

    def test_map_profile_kakao(self):
        from src.auth.oauth_provider import OAuthProvider
        provider = OAuthProvider('kakao')
        raw = {
            'id': 'k456',
            'kakao_account': {
                'email': 'user@kakao.com',
                'profile': {
                    'nickname': 'KakaoUser',
                    'profile_image_url': 'https://pic.url/kakao.jpg',
                },
            },
        }
        mapped = provider.map_profile(raw, 'kakao')
        assert mapped['id'] == 'k456'
        assert mapped['email'] == 'user@kakao.com'
        assert mapped['name'] == 'KakaoUser'
        assert mapped['provider'] == 'kakao'
        assert mapped['avatar_url'] == 'https://pic.url/kakao.jpg'

    def test_unsupported_provider_raises_value_error(self):
        from src.auth.oauth_provider import OAuthProvider
        with pytest.raises(ValueError, match="Unsupported provider"):
            OAuthProvider('facebook')


# ──────────────────────────────────────────────────────────
# TestAuthAPIBlueprint
# ──────────────────────────────────────────────────────────

@pytest.fixture
def auth_client(monkeypatch):
    """Flask test client with auth_api_bp registered."""
    monkeypatch.setenv('AUTH_DEMO_MODE', '1')
    from flask import Flask
    from src.api.auth_api import auth_api_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(auth_api_bp)
    with app.test_client() as c:
        yield c


class TestAuthAPIBlueprint:

    def test_login_returns_200(self, auth_client):
        resp = auth_client.post(
            '/api/v1/auth/login',
            json={'username': 'alice', 'password': 'secret'},
        )
        assert resp.status_code == 200

    def test_login_returns_access_token(self, auth_client):
        resp = auth_client.post(
            '/api/v1/auth/login',
            json={'username': 'alice', 'password': 'secret'},
        )
        data = resp.get_json()
        assert 'access_token' in data
        assert len(data['access_token'].split('.')) == 3

    def test_list_api_keys_returns_list(self, auth_client):
        resp = auth_client.get('/api/v1/auth/api-keys')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'keys' in data
        assert isinstance(data['keys'], list)
