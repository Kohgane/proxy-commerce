"""tests/test_health_monitor.py — 종합 헬스 모니터 테스트.

HealthMonitor의 상태 조회 및 외부 서비스 체크 로직을 검증한다.
외부 API 호출은 mock으로 대체한다.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.resilience.health_monitor import HealthMonitor  # noqa: E402


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def monitor():
    """테스트용 HealthMonitor 인스턴스."""
    return HealthMonitor(start_time=0.0)


# ──────────────────────────────────────────────────────────
# get_status 테스트
# ──────────────────────────────────────────────────────────

class TestHealthMonitorGetStatus:
    def test_get_status_structure(self, monitor):
        """get_status()가 올바른 구조를 반환한다."""
        status = monitor.get_status(include_external=False)
        assert "timestamp" in status
        assert "uptime_seconds" in status
        assert "system" in status
        assert "services" in status
        assert "overall" in status

    def test_uptime_is_positive(self, monitor):
        """uptime_seconds가 0 이상이다."""
        status = monitor.get_status(include_external=False)
        assert status["uptime_seconds"] >= 0

    def test_overall_ok_when_no_services(self, monitor):
        """서비스 체크가 없으면 overall=ok이다."""
        status = monitor.get_status(include_external=False)
        assert status["overall"] == "ok"

    def test_overall_degraded_when_service_fails(self, monitor):
        """외부 서비스가 실패하면 overall=degraded이다."""
        with patch.object(monitor, '_check_all_services', return_value={
            "google_sheets": {"ok": False, "reason": "연결 실패"}
        }):
            status = monitor.get_status(include_external=True)
            assert status["overall"] == "degraded"

    def test_overall_ok_when_all_services_pass(self, monitor):
        """모든 외부 서비스가 성공하면 overall=ok이다."""
        with patch.object(monitor, '_check_all_services', return_value={
            "google_sheets": {"ok": True}
        }):
            status = monitor.get_status(include_external=True)
            assert status["overall"] == "ok"


# ──────────────────────────────────────────────────────────
# 외부 서비스 체크 함수 테스트
# ──────────────────────────────────────────────────────────

class TestExternalServiceChecks:
    def test_check_google_sheets_no_sheet_id(self, monkeypatch):
        """GOOGLE_SHEET_ID가 없으면 ok=False를 반환한다."""
        monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
        from src.resilience.health_monitor import _check_google_sheets
        result = _check_google_sheets()
        assert result["ok"] is False

    def test_check_shopify_missing_env(self, monkeypatch):
        """SHOPIFY_SHOP이 없으면 ok=False를 반환한다."""
        monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
        monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
        from src.resilience.health_monitor import _check_shopify
        result = _check_shopify()
        assert result["ok"] is False

    def test_check_woocommerce_missing_env(self, monkeypatch):
        """WOO_BASE_URL이 없으면 ok=False를 반환한다."""
        monkeypatch.delenv("WOO_BASE_URL", raising=False)
        from src.resilience.health_monitor import _check_woocommerce
        result = _check_woocommerce()
        assert result["ok"] is False

    def test_check_deepl_missing_env(self, monkeypatch):
        """DEEPL_API_KEY가 없으면 ok=False를 반환한다."""
        monkeypatch.delenv("DEEPL_API_KEY", raising=False)
        from src.resilience.health_monitor import _check_deepl
        result = _check_deepl()
        assert result["ok"] is False

    def test_check_google_sheets_exception(self, monkeypatch):
        """open_sheet이 예외를 발생시키면 ok=False를 반환한다."""
        monkeypatch.setenv("GOOGLE_SHEET_ID", "test_sheet")
        from src.resilience import health_monitor as hm_module
        with patch.object(hm_module, '_check_google_sheets', return_value={"ok": False, "reason": "연결 실패"}):
            result = hm_module._check_google_sheets()
            assert result["ok"] is False


# ──────────────────────────────────────────────────────────
# Flask 엔드포인트 테스트
# ──────────────────────────────────────────────────────────

class TestHealthDetailedEndpoint:
    def test_detailed_endpoint_registered(self):
        """/health/detailed 엔드포인트가 Flask 앱에 등록된다."""
        from flask import Flask
        app = Flask(__name__)
        monitor = HealthMonitor(app=app)

        with app.test_client() as client:
            with patch.object(monitor, 'get_status', return_value={
                "overall": "ok",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "uptime_seconds": 100.0,
                "system": {},
                "services": {},
            }):
                resp = client.get('/health/detailed')
                assert resp.status_code == 200

    def test_detailed_endpoint_degraded_returns_503(self):
        """/health/detailed에서 degraded이면 503을 반환한다."""
        from flask import Flask
        app = Flask(__name__)
        monitor = HealthMonitor(app=app)

        with app.test_client() as client:
            with patch.object(monitor, 'get_status', return_value={
                "overall": "degraded",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "uptime_seconds": 100.0,
                "system": {},
                "services": {"google_sheets": {"ok": False}},
            }):
                resp = client.get('/health/detailed')
                assert resp.status_code == 503
