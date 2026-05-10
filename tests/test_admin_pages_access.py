"""tests/test_admin_pages_access.py — admin/non-admin 페이지 접근 테스트 (Phase 142)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_app():
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


class TestAdminDiagnosticsAccess:
    def test_unauthenticated_redirects(self):
        app = _make_app()
        client = app.test_client()
        resp = client.get("/admin/diagnostics")
        assert resp.status_code in (302, 403)

    def test_seller_role_rejected(self):
        app = _make_app()
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = "uid1"
                sess["user_role"] = "seller"
                sess["user_email"] = "user@example.com"
        resp = client.get("/admin/diagnostics")
        assert resp.status_code in (302, 403)

    def test_admin_role_allowed(self):
        app = _make_app()
        _patches = [
            patch("src.dashboard.admin_views._build_env_matrix", return_value=[]),
            patch("src.dashboard.admin_views._build_emergency_access_status", return_value={
                "magic_link_url": "/auth/magic-link",
                "bootstrap_configured": False,
                "bootstrap_url": "/auth/bootstrap",
                "admin_emails_configured": True,
                "issued_magic_link": None,
                "diagnostic_issue_url": "/auth/diagnostic?token=x",
                "diagnostic_reveal_enabled": False,
                "diagnostic_active_count": 0,
                "diagnostic_latest_issued_at": None,
                "diagnostic_worker_pid": "1",
                "diagnostic_web_concurrency": "1",
                "diagnostic_nonce_cache_size": 0,
                "diagnostic_issued_last_hour": 0,
                "diagnostic_redeemed_last_hour": 0,
                "bootstrap_masked_prefix": None,
            }),
            patch("src.dashboard.admin_views._build_oauth_diagnostics", return_value=[]),
            patch("src.dashboard.admin_views._build_messenger_health", return_value={}),
            patch("src.dashboard.admin_views._build_market_health", return_value={}),
            patch("src.dashboard.admin_views._build_pricing_status", return_value={
                "active_rules": 0, "dry_run": True, "cron_hour": "3",
                "last_run_at": None, "min_margin_pct": "15", "fx_trigger_pct": "3",
                "competitor_monitored": 0, "own_changes_24h": 0, "competitor_changes_24h": 0,
                "margin_warnings": 0, "fx_summary": "정상", "auto_apply": False,
                "auto_apply_threshold_pct": "5", "persistence_health": [],
            }),
            patch("src.dashboard.admin_views._build_cs_bot_status", return_value={
                "faq_total": 0, "faq_enabled": 0, "new_24h": 0, "unanswered": 0,
                "urgent_unanswered": 0, "avg_response_minutes": 0, "response_rate": 0,
                "ai_calls_24h": 0, "budget_remaining_pct": 100, "auto_send": False,
                "sla_nearing": 0, "sla_overdue": 0, "channels": [],
                "auto_send_categories": [], "auto_send_daily_limit": 20,
                "auto_send_used_today": 0, "embedding_cached": "0/0",
                "ai_adoption_rate": 0, "ai_edit_rate": 0, "low_quality_count": 0,
                "translation_cache_count": 0, "faq_by_lang": {},
                "scheduler_running": False, "scheduler_enabled": False,
                "scheduler_next_poll": None, "scheduler_next_sla": None,
                "scheduler_jobs": [], "scheduler_missed_24h": 0,
                "scheduler_leader_pid": "-", "scheduler_leader_hostname": "-",
            }),
            patch("src.dashboard.admin_views._build_message_log", return_value={
                "total": 0, "by_channel": {}, "top_errors": [],
            }),
            patch("src.dashboard.admin_views._build_auth_status", return_value={
                "user_email": "admin@example.com", "user_name": "Admin",
                "is_admin": True, "admin_rule": "session_role",
                "admin_emails_configured": True,
                "admin_kakao_configured": False,
                "admin_google_configured": False,
                "admin_naver_configured": False,
                "kakao_oauth_active": False,
                "google_oauth_active": False,
                "naver_oauth_active": False,
                "google_client_id_hint": "미설정",
                "google_redirect_uri": "https://example.com/auth/google/callback",
                "flash_isolation_enabled": True,
            }),
            patch("src.dashboard.admin_views._build_auto_reorder_status", return_value={
                "enabled": False, "auto_place": False, "daily_budget_krw": 500000,
                "safety_days": 14, "pending_count": 0, "estimated_cost_krw": 0,
                "last_checked_ago": "알 수 없음",
            }),
            patch("src.dashboard.admin_views._build_discount_campaign_status", return_value={
                "enabled": False, "max_pct": 20, "margin_floor_pct": 10,
                "recommended_count": 0, "active_count": 0, "overstocked_skus": 0,
            }),
        ]
        with patch.dict(os.environ, {"ADMIN_EMAILS": "admin@example.com"}):
            for p in _patches:
                p.start()
            try:
                with app.test_client() as client:
                    with client.session_transaction() as sess:
                        sess["user_id"] = "admin-001"
                        sess["user_role"] = "admin"
                        sess["user_email"] = "admin@example.com"
                    resp = client.get("/admin/diagnostics")
            finally:
                for p in _patches:
                    p.stop()
        assert resp.status_code == 200

    def test_admin_by_email_env_allowed(self, monkeypatch):
        """ADMIN_EMAILS에 있는 이메일이면 user_role이 'seller'여도 admin으로 진입 가능."""
        app = _make_app()
        monkeypatch.setenv("ADMIN_EMAILS", "shanks8@hanmail.net")

        _patches = [
            patch("src.dashboard.admin_views._build_env_matrix", return_value=[]),
            patch("src.dashboard.admin_views._build_emergency_access_status", return_value={
                "magic_link_url": "/auth/magic-link",
                "bootstrap_configured": False,
                "bootstrap_url": "/auth/bootstrap",
                "admin_emails_configured": True,
                "issued_magic_link": None,
                "diagnostic_issue_url": "/auth/diagnostic?token=x",
                "diagnostic_reveal_enabled": False,
                "diagnostic_active_count": 0,
                "diagnostic_latest_issued_at": None,
                "diagnostic_worker_pid": "1",
                "diagnostic_web_concurrency": "1",
                "diagnostic_nonce_cache_size": 0,
                "diagnostic_issued_last_hour": 0,
                "diagnostic_redeemed_last_hour": 0,
                "bootstrap_masked_prefix": None,
            }),
            patch("src.dashboard.admin_views._build_oauth_diagnostics", return_value=[]),
            patch("src.dashboard.admin_views._build_messenger_health", return_value={}),
            patch("src.dashboard.admin_views._build_market_health", return_value={}),
            patch("src.dashboard.admin_views._build_pricing_status", return_value={
                "active_rules": 0, "dry_run": True, "cron_hour": "3",
                "last_run_at": None, "min_margin_pct": "15", "fx_trigger_pct": "3",
                "competitor_monitored": 0, "own_changes_24h": 0, "competitor_changes_24h": 0,
                "margin_warnings": 0, "fx_summary": "정상", "auto_apply": False,
                "auto_apply_threshold_pct": "5", "persistence_health": [],
            }),
            patch("src.dashboard.admin_views._build_cs_bot_status", return_value={
                "faq_total": 0, "faq_enabled": 0, "new_24h": 0, "unanswered": 0,
                "urgent_unanswered": 0, "avg_response_minutes": 0, "response_rate": 0,
                "ai_calls_24h": 0, "budget_remaining_pct": 100, "auto_send": False,
                "sla_nearing": 0, "sla_overdue": 0, "channels": [],
                "auto_send_categories": [], "auto_send_daily_limit": 20,
                "auto_send_used_today": 0, "embedding_cached": "0/0",
                "ai_adoption_rate": 0, "ai_edit_rate": 0, "low_quality_count": 0,
                "translation_cache_count": 0, "faq_by_lang": {},
                "scheduler_running": False, "scheduler_enabled": False,
                "scheduler_next_poll": None, "scheduler_next_sla": None,
                "scheduler_jobs": [], "scheduler_missed_24h": 0,
                "scheduler_leader_pid": "-", "scheduler_leader_hostname": "-",
            }),
            patch("src.dashboard.admin_views._build_message_log", return_value={
                "total": 0, "by_channel": {}, "top_errors": [],
            }),
            patch("src.dashboard.admin_views._build_auth_status", return_value={
                "user_email": "shanks8@hanmail.net", "user_name": "Admin",
                "is_admin": True, "admin_rule": "ADMIN_EMAILS",
                "admin_emails_configured": True,
                "admin_kakao_configured": False,
                "admin_google_configured": False,
                "admin_naver_configured": False,
                "kakao_oauth_active": False,
                "google_oauth_active": False,
                "naver_oauth_active": False,
                "google_client_id_hint": "미설정",
                "google_redirect_uri": "https://example.com/auth/google/callback",
                "flash_isolation_enabled": True,
            }),
            patch("src.dashboard.admin_views._build_auto_reorder_status", return_value={
                "enabled": False, "auto_place": False, "daily_budget_krw": 500000,
                "safety_days": 14, "pending_count": 0, "estimated_cost_krw": 0,
                "last_checked_ago": "알 수 없음",
            }),
            patch("src.dashboard.admin_views._build_discount_campaign_status", return_value={
                "enabled": False, "max_pct": 20, "margin_floor_pct": 10,
                "recommended_count": 0, "active_count": 0, "overstocked_skus": 0,
            }),
        ]
        for p in _patches:
            p.start()
        try:
            with app.test_client() as client:
                with client.session_transaction() as sess:
                    sess["user_id"] = "uid1"
                    sess["user_role"] = "seller"  # DB role is seller
                    sess["user_email"] = "shanks8@hanmail.net"  # but email is in ADMIN_EMAILS
                resp = client.get("/admin/diagnostics")
        finally:
            for p in _patches:
                p.stop()
        # Should be 200 because ADMIN_EMAILS check in is_admin_session passes
        assert resp.status_code == 200
