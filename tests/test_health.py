"""
tests/test_health.py — Healthcheck 엔드포인트 테스트.

GET /health       → 200, {"status": "ok", "service": "proxy-commerce", "version": ...}
GET /health/ready → 항상 200 반환 (soft-fail)
                    - optional 시크릿 미설정: {"status":"ready","degraded":true}
                    - 모든 시크릿 설정:     {"status":"ready","degraded":false}
"""

import json
from unittest.mock import patch

import pytest


# ── Flask test client ─────────────────────────────────────────────────────────

@pytest.fixture
def client():
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    with wh.app.test_client() as c:
        yield c


# ══════════════════════════════════════════════════════════
# GET /health
# ══════════════════════════════════════════════════════════

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200

    def test_health_returns_json(self, client):
        resp = client.get('/health')
        data = json.loads(resp.data)
        assert data['status'] == 'ok'

    def test_health_service_name(self, client):
        resp = client.get('/health')
        data = json.loads(resp.data)
        assert data['service'] == 'proxy-commerce'

    def test_health_version_default(self, client):
        """APP_VERSION 환경변수 미설정 시 'dev' 반환."""
        import os
        os.environ.pop('APP_VERSION', None)
        resp = client.get('/health')
        data = json.loads(resp.data)
        assert data['version'] == 'dev'

    def test_health_version_from_env(self, client):
        """APP_VERSION 환경변수 설정 시 해당 값 반환."""
        with patch.dict('os.environ', {'APP_VERSION': '1.2.3'}):
            resp = client.get('/health')
            data = json.loads(resp.data)
            assert data['version'] == '1.2.3'


# ══════════════════════════════════════════════════════════
# GET /health/ready — soft-fail 동작
# ══════════════════════════════════════════════════════════

class TestReadinessEndpoint:
    def test_readiness_returns_json(self, client):
        resp = client.get('/health/ready')
        data = json.loads(resp.data)
        assert 'status' in data
        assert 'checks' in data

    def test_readiness_200_when_secrets_ok(self, client):
        """core secrets가 설정되어 있으면 200 + ready + degraded:false."""
        mock_result = {'core': {'set': ['GOOGLE_SERVICE_JSON_B64', 'GOOGLE_SHEET_ID'], 'missing': []}}
        with patch('src.utils.secret_check.check_secrets', return_value=mock_result):
            resp = client.get('/health/ready')
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data['status'] == 'ready'
            assert data['checks']['secrets_core'] is True
            assert data['degraded'] is False

    def test_readiness_200_when_secrets_missing(self, client):
        """optional 시크릿 미설정 시에도 HTTP 200 반환 (soft-fail), degraded:true."""
        mock_result = {'core': {'set': [], 'missing': ['GOOGLE_SERVICE_JSON_B64', 'GOOGLE_SHEET_ID']}}
        with patch('src.utils.secret_check.check_secrets', return_value=mock_result):
            resp = client.get('/health/ready')
            # soft-fail: 503 대신 200 반환
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data['status'] == 'ready'
            assert data['degraded'] is True
            assert data['checks']['secrets_core'] is False

    def test_readiness_200_on_exception(self, client):
        """check_secrets 예외 발생 시에도 200 + degraded:true (soft-fail)."""
        with patch('src.utils.secret_check.check_secrets', side_effect=Exception('connection failed')):
            resp = client.get('/health/ready')
            # soft-fail: 예외 발생해도 503 대신 200 반환
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data['status'] == 'ready'
            assert data['degraded'] is True
            assert data['checks']['secrets_core'] is False

    def test_readiness_checks_key_present(self, client):
        """응답 JSON에 checks 딕셔너리와 degraded 필드가 포함되어야 함."""
        resp = client.get('/health/ready')
        data = json.loads(resp.data)
        assert isinstance(data['checks'], dict)
        assert 'secrets_core' in data['checks']
        assert 'degraded' in data

    def test_readiness_degraded_field_is_bool(self, client):
        """degraded 필드는 항상 bool 타입이어야 함."""
        resp = client.get('/health/ready')
        data = json.loads(resp.data)
        assert isinstance(data['degraded'], bool)
