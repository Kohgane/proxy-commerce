"""tests/test_api_auth.py — API 인증 미들웨어 테스트."""

import os
from unittest.mock import patch, MagicMock

import pytest

from src.api.auth_middleware import require_api_key


@pytest.fixture
def api_app(mock_env):
    """API Blueprint이 등록된 Flask 앱."""
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    # API Blueprint 등록 (이미 등록된 경우 스킵)
    try:
        from src.api import dashboard_bp
        wh.app.register_blueprint(dashboard_bp)
    except Exception:
        pass
    with wh.app.test_client() as c:
        yield c


class TestRequireApiKey:
    """require_api_key 데코레이터 테스트."""

    def test_no_api_key_configured_allows_access(self, api_app, monkeypatch):
        """DASHBOARD_API_KEY 미설정 시 인증 없이 접근 가능."""
        monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
        with patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_app.get("/api/dashboard/health")
        # 비활성화 또는 정상 응답
        assert resp.status_code in (200, 503)

    def test_valid_api_key_allows_access(self, api_app, monkeypatch):
        """올바른 API 키로 접근 허용."""
        monkeypatch.setenv("DASHBOARD_API_KEY", "test-secret-key")
        monkeypatch.setenv("DASHBOARD_API_ENABLED", "1")
        with patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_app.get(
                "/api/dashboard/health",
                headers={"X-API-Key": "test-secret-key"},
            )
        assert resp.status_code in (200, 503)

    def test_invalid_api_key_returns_401(self, api_app, monkeypatch):
        """잘못된 API 키로 접근 시 401 반환."""
        monkeypatch.setenv("DASHBOARD_API_KEY", "correct-key")
        with patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_app.get(
                "/api/dashboard/health",
                headers={"X-API-Key": "wrong-key"},
            )
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "Unauthorized"

    def test_missing_api_key_header_returns_401(self, api_app, monkeypatch):
        """API 키 헤더 없이 접근 시 401 반환."""
        monkeypatch.setenv("DASHBOARD_API_KEY", "correct-key")
        with patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_app.get("/api/dashboard/health")
        assert resp.status_code == 401
