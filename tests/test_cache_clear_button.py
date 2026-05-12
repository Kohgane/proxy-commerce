from __future__ import annotations

from flask import Flask


def _app():
    from src.dashboard.admin_views import admin_panel_bp

    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(admin_panel_bp)
    return app


def test_ai_listing_cache_clear_requires_admin(monkeypatch):
    app = _app()
    monkeypatch.setattr("src.auth.admin_resolver.is_admin_session", lambda sess: (False, None))
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = "u1"
            sess["user_role"] = "seller"
        resp = client.post("/admin/cache/ai_listing/clear")
    assert resp.status_code == 403


def test_ai_listing_cache_clear_json_success(monkeypatch):
    app = _app()
    monkeypatch.setattr("src.auth.admin_resolver.is_admin_session", lambda sess: (True, "ok"))
    monkeypatch.setattr("src.ai_listing.analyzer.clear_all_analysis_cache", lambda: 2)
    monkeypatch.setattr("src.dashboard.admin_views._scan_merge_conflict_marker_count", lambda: 0)
    monkeypatch.setattr("src.dashboard.admin_views._scan_python_syntax_error_count", lambda: 0)
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = "admin"
            sess["user_role"] = "admin"
        resp = client.post("/admin/cache/ai_listing/clear")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["deleted_analysis"] == 2
