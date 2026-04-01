"""tests/test_monitoring.py — 모니터링 모듈 테스트."""
from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# 패키지 임포트 경로 보정
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.monitoring.metrics import MetricsCollector
from src.monitoring.health import HealthChecker
from src.monitoring.alerts import AlertRule, AlertManager


# ===========================================================================
# MetricsCollector
# ===========================================================================

class TestMetricsCollector:
    def setup_method(self):
        self.m = MetricsCollector()

    def test_increment_counter(self):
        self.m.increment("orders_total")
        self.m.increment("orders_total")
        assert self.m.get_counter("orders_total") == 2

    def test_increment_counter_with_value(self):
        self.m.increment("orders_total", value=5)
        assert self.m.get_counter("orders_total") == 5

    def test_observe_histogram(self):
        self.m.observe("api_latency_seconds", 0.5)
        self.m.observe("api_latency_seconds", 1.5)
        stats = self.m.get_histogram_stats("api_latency_seconds")
        assert stats["count"] == 2
        assert stats["sum"] == pytest.approx(2.0)

    def test_set_gauge_and_get_gauge(self):
        self.m.set_gauge("active_products", 42.0)
        assert self.m.get_gauge("active_products") == pytest.approx(42.0)

    def test_get_gauge_default(self):
        assert self.m.get_gauge("nonexistent") == pytest.approx(0.0)

    def test_get_histogram_stats(self):
        self.m.observe("api_latency_seconds", 1.0)
        self.m.observe("api_latency_seconds", 3.0)
        stats = self.m.get_histogram_stats("api_latency_seconds")
        assert stats["count"] == 2
        assert stats["avg"] == pytest.approx(2.0)
        assert stats["min"] == pytest.approx(1.0)
        assert stats["max"] == pytest.approx(3.0)

    def test_get_histogram_stats_empty(self):
        stats = self.m.get_histogram_stats("nonexistent")
        assert stats["count"] == 0
        assert stats["avg"] == 0.0

    def test_export_prometheus_text_format(self):
        self.m.increment("orders_total", 3)
        self.m.set_gauge("active_products", 10.0)
        text = self.m.export_prometheus_text()
        assert "# HELP orders_total" in text
        assert "# TYPE orders_total counter" in text
        assert "orders_total 3" in text
        assert "# TYPE active_products gauge" in text
        assert "active_products 10.0" in text

    def test_export_prometheus_text_histogram(self):
        self.m.observe("api_latency_seconds", 0.3)
        self.m.observe("api_latency_seconds", 0.7)
        text = self.m.export_prometheus_text()
        assert "# TYPE api_latency_seconds histogram" in text
        assert "api_latency_seconds_sum" in text
        assert "api_latency_seconds_count" in text

    def test_reset_clears_all(self):
        self.m.increment("orders_total", 5)
        self.m.observe("api_latency_seconds", 1.0)
        self.m.set_gauge("active_products", 7.0)
        self.m.reset()
        assert self.m.get_counter("orders_total") == 0
        assert self.m.get_histogram_stats("api_latency_seconds")["count"] == 0
        assert self.m.get_gauge("active_products") == 0.0


# ===========================================================================
# HealthChecker
# ===========================================================================

class TestHealthChecker:
    def setup_method(self):
        self.hc = HealthChecker()

    def test_check_database_none_returns_unconfigured(self):
        result = self.hc.check_database(None)
        assert result["status"] == "unconfigured"

    def test_check_database_empty_returns_unconfigured(self):
        result = self.hc.check_database("")
        assert result["status"] == "unconfigured"

    def test_check_database_valid_url(self):
        result = self.hc.check_database("postgresql://user:pass@localhost/db")
        assert result["status"] == "ok"
        assert "latency_ms" in result

    def test_check_redis_none_returns_unconfigured(self):
        result = self.hc.check_redis(None)
        assert result["status"] == "unconfigured"

    def test_check_redis_valid_url(self):
        result = self.hc.check_redis("redis://localhost:6379/0")
        assert result["status"] == "ok"

    @patch("src.monitoring.health.requests.head")
    def test_check_external_api_success(self, mock_head):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_head.return_value = mock_resp
        result = self.hc.check_external_api("https://example.com")
        assert result["status"] == "ok"
        assert "latency_ms" in result

    @patch("src.monitoring.health.requests.head")
    def test_check_external_api_failure(self, mock_head):
        mock_head.side_effect = Exception("Connection refused")
        result = self.hc.check_external_api("https://unreachable.example.com")
        assert result["status"] == "error"
        assert "latency_ms" in result

    def test_run_all_checks_with_mixed_results(self):
        checks = {
            "db": lambda: {"status": "ok"},
            "redis": lambda: {"status": "error"},
        }
        result = self.hc.run_all_checks(checks)
        assert result["status"] == "degraded"
        assert "checks" in result
        assert "timestamp" in result

    def test_run_all_checks_all_ok(self):
        checks = {
            "db": lambda: {"status": "ok"},
        }
        result = self.hc.run_all_checks(checks)
        assert result["status"] == "healthy"

    def test_run_all_checks_all_error(self):
        checks = {
            "db": lambda: {"status": "error"},
            "redis": lambda: {"status": "error"},
        }
        result = self.hc.run_all_checks(checks)
        assert result["status"] == "unhealthy"

    def test_run_all_checks_empty(self):
        result = self.hc.run_all_checks()
        assert result["status"] == "healthy"


# ===========================================================================
# AlertRule
# ===========================================================================

class TestAlertRule:
    def test_dataclass_creation(self):
        rule = AlertRule(name="test_rule", metric="errors_total", threshold=50.0)
        assert rule.name == "test_rule"
        assert rule.metric == "errors_total"
        assert rule.threshold == 50.0
        assert rule.operator == ">"
        assert rule.message_template == ""

    def test_dataclass_with_all_fields(self):
        rule = AlertRule(
            name="r",
            metric="m",
            threshold=1.0,
            operator=">=",
            message_template="Alert: {value}",
        )
        assert rule.operator == ">="
        assert rule.message_template == "Alert: {value}"


# ===========================================================================
# AlertManager
# ===========================================================================

class TestAlertManager:
    def setup_method(self):
        self.manager = AlertManager()
        self.metrics = MetricsCollector()

    def test_add_rule(self):
        initial_count = len(self.manager._rules)
        new_rule = AlertRule(name="custom_rule", metric="custom_metric", threshold=10.0)
        self.manager.add_rule(new_rule)
        assert len(self.manager._rules) == initial_count + 1

    def test_evaluate_no_alerts_below_threshold(self):
        # 기본 규칙: errors_total > 100
        self.metrics.increment("errors_total", 10)
        triggered = self.manager.evaluate(self.metrics)
        # errors_total=10 은 threshold=100 을 초과하지 않음
        assert all(a["metric"] != "errors_total" for a in triggered)

    def test_evaluate_triggered_alert(self):
        # errors_total 을 임계값 초과로 설정
        self.metrics.increment("errors_total", 200)
        triggered = self.manager.evaluate(self.metrics)
        names = [a["rule"] for a in triggered]
        assert "error_rate_high" in names
        alert = next(a for a in triggered if a["rule"] == "error_rate_high")
        assert alert["triggered"] is True
        assert alert["value"] == 200.0

    def test_evaluate_and_notify_calls_notifier_when_triggered(self):
        mock_notifier = MagicMock()
        manager = AlertManager(notifier=mock_notifier)
        metrics = MetricsCollector()
        metrics.increment("errors_total", 999)
        triggered = manager.evaluate_and_notify(metrics)
        assert len(triggered) > 0
        mock_notifier.send_message.assert_called()

    def test_evaluate_and_notify_no_call_when_no_trigger(self):
        mock_notifier = MagicMock()
        manager = AlertManager(notifier=mock_notifier)
        metrics = MetricsCollector()
        # 모든 메트릭을 임계값 미만으로 유지
        triggered = manager.evaluate_and_notify(metrics)
        mock_notifier.send_message.assert_not_called()


# ===========================================================================
# Monitoring API Blueprint
# ===========================================================================

class TestMonitoringAPIBlueprint:
    @pytest.fixture
    def client(self):
        from flask import Flask
        from src.api.monitoring_api import monitoring_bp
        app = Flask(__name__)
        app.register_blueprint(monitoring_bp)
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_metrics_returns_200_with_text_plain(self, client):
        resp = client.get("/api/v1/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.content_type

    def test_health_returns_200_with_json(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "status" in data
        assert "timestamp" in data
