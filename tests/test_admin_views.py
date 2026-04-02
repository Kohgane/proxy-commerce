"""tests/test_admin_views.py — 관리자 패널 뷰 테스트.

Phase 25: Frontend Admin Panel
"""

import pytest
from flask import Flask


@pytest.fixture
def admin_app(mock_env):
    """관리자 Blueprint가 등록된 Flask 테스트 앱."""
    from src.dashboard.admin_views import admin_panel_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(admin_panel_bp)
    return app


@pytest.fixture
def client(admin_app):
    return admin_app.test_client()


def test_admin_dashboard_returns_200(client):
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert b"</html>" in resp.data


def test_admin_products_returns_200(client):
    resp = client.get("/admin/products")
    assert resp.status_code == 200
    assert b"</html>" in resp.data


def test_admin_orders_returns_200(client):
    resp = client.get("/admin/orders")
    assert resp.status_code == 200
    assert b"</html>" in resp.data


def test_admin_inventory_returns_200(client):
    resp = client.get("/admin/inventory")
    assert resp.status_code == 200
    assert b"</html>" in resp.data
