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


# ══════════════════════════════════════════════════════════
# GET /health/deep — 상세 진단 응답 포맷 검증
# ══════════════════════════════════════════════════════════

class TestDeepHealthResponseFormat:
    def test_deep_health_checks_is_list(self, client):
        """/health/deep 응답의 checks 필드는 list 형식이어야 한다."""
        from unittest.mock import patch, MagicMock
        with patch('src.utils.secret_check.check_secrets') as mock_check, \
             patch('src.utils.sheets.diagnose_sheets_connection') as mock_diag:
            mock_check.return_value = {
                'core': {'set': ['GOOGLE_SERVICE_JSON_B64', 'GOOGLE_SHEET_ID'], 'missing': []}
            }
            mock_diag.return_value = {"status": "ok", "detail": "연결 성공"}
            resp = client.get('/health/deep')
        data = json.loads(resp.data)
        assert isinstance(data['checks'], list)

    def test_deep_health_each_check_has_required_keys(self, client):
        """각 check 항목은 name, status, detail 키를 가져야 한다."""
        from unittest.mock import patch, MagicMock
        with patch('src.utils.secret_check.check_secrets') as mock_check, \
             patch('src.utils.sheets.diagnose_sheets_connection') as mock_diag:
            mock_check.return_value = {
                'core': {'set': ['GOOGLE_SERVICE_JSON_B64', 'GOOGLE_SHEET_ID'], 'missing': []}
            }
            mock_diag.return_value = {"status": "ok", "detail": "연결 성공"}
            resp = client.get('/health/deep')
        data = json.loads(resp.data)
        for check in data['checks']:
            assert 'name' in check
            assert 'status' in check
            assert 'detail' in check

    def test_deep_health_google_sheets_fail_has_hint(self, client):
        """google_sheets fail 케이스에서 hint 필드가 노출되어야 한다."""
        from unittest.mock import patch, MagicMock
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "type": "service_account",
            "project_id": "test-project",
            "private_key": "key",
            "client_email": "svc@test.iam.gserviceaccount.com",
        }
        mock_loader.source = "GOOGLE_SERVICE_JSON_B64"
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"  # 유효한 길이의 ID
        with patch('src.utils.secret_check.check_secrets') as mock_check, \
             patch('src.utils.google_credentials.GoogleCredentialsLoader', return_value=mock_loader), \
             patch('src.utils.sheets.diagnose_sheets_connection') as mock_diag, \
             patch.dict('os.environ', {'GOOGLE_SHEET_ID': sheet_id}):
            mock_check.return_value = {
                'core': {'set': ['GOOGLE_SERVICE_JSON_B64', 'GOOGLE_SHEET_ID'], 'missing': []}
            }
            mock_diag.return_value = {
                "status": "fail",
                "detail": "permission denied — 시트 접근 권한 없음",
                "hint": "시트의 공유 메뉴에서 서비스계정 이메일을 편집자로 추가",
            }
            resp = client.get('/health/deep')
        data = json.loads(resp.data)
        sheets_check = next(
            (c for c in data['checks'] if c['name'] == 'google_sheets'), None
        )
        assert sheets_check is not None
        assert sheets_check['status'] == 'fail'
        assert 'hint' in sheets_check

    def test_deep_health_has_timestamp(self, client):
        """/health/deep 응답에 timestamp 필드가 있어야 한다."""
        from unittest.mock import patch
        with patch('src.utils.sheets.diagnose_sheets_connection') as mock_diag:
            mock_diag.return_value = {"status": "skip", "detail": "미설정"}
            resp = client.get('/health/deep')
        data = json.loads(resp.data)
        assert 'timestamp' in data

    def test_deep_health_has_google_credentials_check(self, client):
        """/health/deep 응답에 google_credentials check가 있어야 한다."""
        from unittest.mock import patch, MagicMock
        from src.utils.google_credentials import CredentialsLoadError
        with patch('src.utils.google_credentials.GoogleCredentialsLoader.load',
                   side_effect=CredentialsLoadError("자격증명 없음")):
            resp = client.get('/health/deep')
        data = json.loads(resp.data)
        names = [c['name'] for c in data['checks']]
        assert 'google_credentials' in names

    def test_deep_health_credentials_fail_skips_sheets(self, client):
        """google_credentials fail 시 google_sheets는 skip이어야 한다."""
        from unittest.mock import patch
        from src.utils.google_credentials import CredentialsLoadError
        with patch('src.utils.google_credentials.GoogleCredentialsLoader.load',
                   side_effect=CredentialsLoadError("no creds")):
            resp = client.get('/health/deep')
        data = json.loads(resp.data)
        sheets_check = next((c for c in data['checks'] if c['name'] == 'google_sheets'), None)
        assert sheets_check is not None
        assert sheets_check['status'] == 'skip'

    def test_deep_health_credentials_ok_shows_source(self, client):
        """google_credentials ok 시 source 필드가 노출되어야 한다."""
        from unittest.mock import patch, MagicMock
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "type": "service_account",
            "project_id": "test-project",
            "private_key": "key",
            "client_email": "svc@test.iam.gserviceaccount.com",
        }
        mock_loader.source = "GOOGLE_SERVICE_JSON_B64"
        with patch('src.utils.google_credentials.GoogleCredentialsLoader', return_value=mock_loader), \
             patch('src.utils.sheets.diagnose_sheets_connection',
                   return_value={"status": "ok", "detail": "연결 성공", "service_account": "svc@test.iam.gserviceaccount.com"}):
            resp = client.get('/health/deep')
        data = json.loads(resp.data)
        cred_check = next((c for c in data['checks'] if c['name'] == 'google_credentials'), None)
        assert cred_check is not None
        assert cred_check['status'] == 'ok'
        assert 'source' in cred_check

    def test_deep_health_has_uptime_seconds(self, client):
        """/health/deep 응답에 uptime_seconds 필드가 있어야 한다."""
        from unittest.mock import patch
        with patch('src.utils.sheets.diagnose_sheets_connection') as mock_diag:
            mock_diag.return_value = {"status": "skip", "detail": "미설정"}
            resp = client.get('/health/deep')
        data = json.loads(resp.data)
        assert 'uptime_seconds' in data
        assert isinstance(data['uptime_seconds'], (int, float))
