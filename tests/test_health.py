"""
tests/test_health.py — Healthcheck 엔드포인트 테스트.

GET /health       → 200, {"status": "ok", "service": "proxy-commerce", "version": ...}
GET /health/ready → 200 (core secrets 설정 시) 또는 503 (미설정 시)
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
# GET /health/ready
# ══════════════════════════════════════════════════════════

class TestReadinessEndpoint:
    def test_readiness_returns_json(self, client):
        resp = client.get('/health/ready')
        data = json.loads(resp.data)
        assert 'status' in data
        assert 'checks' in data

    def test_readiness_200_when_secrets_ok(self, client):
        """core secrets가 설정되어 있으면 200 + ready."""
        mock_result = {'core': {'set': ['GOOGLE_SERVICE_JSON_B64', 'GOOGLE_SHEET_ID'], 'missing': []}}
        with patch('src.utils.secret_check.check_secrets', return_value=mock_result):
            resp = client.get('/health/ready')
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data['status'] == 'ready'
            assert data['checks']['secrets_core'] is True

    def test_readiness_503_when_secrets_missing(self, client):
        """core secrets 미설정 시 503 + not_ready."""
        mock_result = {'core': {'set': [], 'missing': ['GOOGLE_SERVICE_JSON_B64', 'GOOGLE_SHEET_ID']}}
        with patch('src.utils.secret_check.check_secrets', return_value=mock_result):
            resp = client.get('/health/ready')
            assert resp.status_code == 503
            data = json.loads(resp.data)
            assert data['status'] == 'not_ready'
            assert data['checks']['secrets_core'] is False

    def test_readiness_503_on_exception(self, client):
        """check_secrets 예외 발생 시 503 + not_ready (graceful degradation)."""
        with patch('src.utils.secret_check.check_secrets', side_effect=Exception('connection failed')):
            resp = client.get('/health/ready')
            assert resp.status_code == 503
            data = json.loads(resp.data)
            assert data['status'] == 'not_ready'
            assert data['checks']['secrets_core'] is False

    def test_readiness_checks_key_present(self, client):
        """응답 JSON에 checks 딕셔너리가 포함되어야 함."""
        resp = client.get('/health/ready')
        data = json.loads(resp.data)
        assert isinstance(data['checks'], dict)
        assert 'secrets_core' in data['checks']
