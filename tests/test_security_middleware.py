"""tests/test_security_middleware.py — 보안 미들웨어 테스트.

SecurityMiddleware의 보안 헤더 추가, Content-Type 검증,
RequestLogger의 요청 ID 생성 및 민감 데이터 마스킹을 검증한다.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.middleware.security import SecurityMiddleware
from src.middleware.request_logger import RequestLogger, _mask_dict


# ──────────────────────────────────────────────────────────
# SecurityMiddleware 테스트
# ──────────────────────────────────────────────────────────

@pytest.fixture
def secure_app():
    """SecurityMiddleware가 적용된 Flask 테스트 앱."""
    from flask import Flask, jsonify
    app = Flask(__name__)
    app.config['TESTING'] = True
    SecurityMiddleware(app)

    @app.get('/test')
    def test_endpoint():
        return jsonify({"ok": True})

    @app.post('/test')
    def test_post():
        return jsonify({"ok": True})

    return app


class TestSecurityHeaders:
    def test_x_content_type_options_header(self, secure_app):
        """X-Content-Type-Options: nosniff 헤더가 추가된다."""
        with secure_app.test_client() as client:
            resp = client.get('/test')
            assert resp.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_x_frame_options_header(self, secure_app):
        """X-Frame-Options: DENY 헤더가 추가된다."""
        with secure_app.test_client() as client:
            resp = client.get('/test')
            assert resp.headers.get('X-Frame-Options') == 'DENY'

    def test_x_xss_protection_header(self, secure_app):
        """X-XSS-Protection 헤더가 추가된다."""
        with secure_app.test_client() as client:
            resp = client.get('/test')
            assert resp.headers.get('X-XSS-Protection') == '1; mode=block'

    def test_referrer_policy_header(self, secure_app):
        """Referrer-Policy 헤더가 추가된다."""
        with secure_app.test_client() as client:
            resp = client.get('/test')
            assert 'Referrer-Policy' in resp.headers

    def test_csp_header(self, secure_app):
        """Content-Security-Policy 헤더가 추가된다."""
        with secure_app.test_client() as client:
            resp = client.get('/test')
            assert 'Content-Security-Policy' in resp.headers

    def test_post_with_json_content_type_allowed(self, secure_app):
        """application/json Content-Type의 POST는 허용된다."""
        with secure_app.test_client() as client:
            resp = client.post(
                '/test',
                data=json.dumps({"key": "value"}),
                content_type='application/json',
            )
            assert resp.status_code == 200

    def test_post_with_unsupported_content_type_rejected(self, secure_app):
        """지원되지 않는 Content-Type의 POST는 415를 반환한다."""
        with secure_app.test_client() as client:
            resp = client.post(
                '/test',
                data="raw data",
                content_type='application/octet-stream',
                headers={'Content-Length': '8'},
            )
            assert resp.status_code == 415


# ──────────────────────────────────────────────────────────
# RequestLogger 테스트
# ──────────────────────────────────────────────────────────

@pytest.fixture
def logged_app():
    """RequestLogger가 적용된 Flask 테스트 앱."""
    from flask import Flask, jsonify
    app = Flask(__name__)
    app.config['TESTING'] = True
    RequestLogger(app)

    @app.get('/test')
    def test_endpoint():
        return jsonify({"ok": True})

    return app


class TestRequestLogger:
    def test_request_id_header_added(self, logged_app):
        """응답에 X-Request-ID 헤더가 추가된다."""
        with logged_app.test_client() as client:
            resp = client.get('/test')
            assert 'X-Request-ID' in resp.headers

    def test_request_id_is_uuid_format(self, logged_app):
        """X-Request-ID가 UUID 형식이다."""
        import uuid
        with logged_app.test_client() as client:
            resp = client.get('/test')
            req_id = resp.headers.get('X-Request-ID')
            assert req_id is not None
            # UUID 형식 검증 (36자 하이픈 포함)
            try:
                uuid.UUID(req_id)
                valid = True
            except ValueError:
                valid = False
            assert valid

    def test_custom_request_id_preserved(self, logged_app):
        """X-Request-ID 요청 헤더가 있으면 그대로 사용한다."""
        with logged_app.test_client() as client:
            resp = client.get('/test', headers={'X-Request-ID': 'custom-id-12345'})
            assert resp.headers.get('X-Request-ID') == 'custom-id-12345'


# ──────────────────────────────────────────────────────────
# 민감 데이터 마스킹 테스트
# ──────────────────────────────────────────────────────────

class TestSensitiveDataMasking:
    def test_api_key_masked(self):
        """api_key 필드가 마스킹된다."""
        data = {"api_key": "secret-value", "name": "test"}
        masked = _mask_dict(data)
        assert masked["api_key"] == "***MASKED***"
        assert masked["name"] == "test"

    def test_password_masked(self):
        """password 필드가 마스킹된다."""
        data = {"password": "my_password", "user": "admin"}
        masked = _mask_dict(data)
        assert masked["password"] == "***MASKED***"
        assert masked["user"] == "admin"

    def test_token_masked(self):
        """token 필드가 마스킹된다."""
        data = {"token": "abc123", "id": 42}
        masked = _mask_dict(data)
        assert masked["token"] == "***MASKED***"

    def test_nested_dict_masked(self):
        """중첩 딕셔너리도 재귀적으로 마스킹된다."""
        data = {
            "user": {
                "name": "홍길동",
                "api_key": "nested-secret",
            }
        }
        masked = _mask_dict(data)
        assert masked["user"]["api_key"] == "***MASKED***"
        assert masked["user"]["name"] == "홍길동"

    def test_list_items_masked(self):
        """리스트 내 딕셔너리도 마스킹된다."""
        data = [{"token": "t1"}, {"token": "t2", "id": 1}]
        masked = _mask_dict(data)
        assert masked[0]["token"] == "***MASKED***"
        assert masked[1]["token"] == "***MASKED***"
        assert masked[1]["id"] == 1

    def test_non_sensitive_fields_unchanged(self):
        """민감하지 않은 필드는 변경되지 않는다."""
        data = {"order_id": 12345, "status": "paid", "total": "59000"}
        masked = _mask_dict(data)
        assert masked == data

    def test_make_request_id_format(self):
        """make_request_id()가 UUID를 반환한다."""
        import uuid
        req_id = RequestLogger.make_request_id()
        uuid.UUID(req_id)  # 예외 없으면 유효한 UUID
