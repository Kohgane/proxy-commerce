"""tests/test_diagnostics_view.py — /admin/diagnostics 진단 대시보드 테스트 (Phase 136)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_app():
    """테스트용 Flask 앱 생성."""
    try:
        from src.order_webhook import app
        return app
    except Exception:
        pass
    from flask import Flask
    from src.dashboard.admin_views import admin_panel_bp
    test_app = Flask(__name__)
    test_app.secret_key = "test-secret"
    test_app.register_blueprint(admin_panel_bp)
    return test_app


class TestDiagnosticsView:
    def test_diagnostics_requires_login(self):
        app = _make_app()
        client = app.test_client()
        resp = client.get("/admin/diagnostics")
        # 비로그인 → 302 로그인 리다이렉트
        assert resp.status_code in (302, 403)

    def test_diagnostics_requires_admin_role(self):
        app = _make_app()
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = "user-123"
                sess["user_role"] = "seller"  # admin 아님
            resp = client.get("/admin/diagnostics")
        assert resp.status_code == 403

    def test_diagnostics_ok_for_admin(self):
        app = _make_app()
        with patch("src.dashboard.admin_views._build_env_matrix", return_value=[]), \
             patch("src.dashboard.admin_views._build_messenger_health", return_value={}), \
             patch("src.dashboard.admin_views._build_market_health", return_value={}), \
             patch("src.dashboard.admin_views._build_pricing_status",
                   return_value={"active_rules": 0, "dry_run": True, "cron_hour": "3",
                                 "last_run_at": None, "min_margin_pct": "15", "fx_trigger_pct": "3"}), \
             patch("src.dashboard.admin_views._build_message_log",
                   return_value={"total": 0, "by_channel": {}, "top_errors": []}):

            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["user_id"] = "admin-001"
                    sess["user_role"] = "admin"
                resp = client.get("/admin/diagnostics")

        assert resp.status_code == 200
        assert b"diagnostics" in resp.data.lower() or "진단".encode() in resp.data

    def test_telegram_health_endpoint(self):
        app = _make_app()
        with patch("src.notifications.telegram.health_check",
                   return_value={"status": "missing", "hint": "TELEGRAM_BOT_TOKEN 미설정"}):
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["user_id"] = "admin-001"
                    sess["user_role"] = "admin"
                resp = client.get("/admin/diagnostics/telegram-health")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "missing"
