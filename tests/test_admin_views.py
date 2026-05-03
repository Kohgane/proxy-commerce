"""tests/test_admin_views.py — 관리자 패널 뷰 테스트.

Phase 25: Frontend Admin Panel
Phase 124: HTML escape 검증 + Bootstrap CDN 로드 확인
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


def test_admin_dashboard_no_escaped_html(client):
    """대시보드 응답 본문에 escaped HTML 태그(&lt;div 등)가 없어야 한다."""
    resp = client.get("/admin/")
    body = resp.data.decode("utf-8")
    # HTML 태그가 escape되지 않아야 함
    assert "&lt;h4" not in body
    assert "&lt;div" not in body
    assert "&lt;span" not in body


def test_admin_dashboard_has_bootstrap_cdn(client):
    """대시보드 응답 <head>에 Bootstrap CDN 링크가 포함되어야 한다."""
    resp = client.get("/admin/")
    body = resp.data.decode("utf-8")
    assert "cdn.jsdelivr.net" in body
    assert "bootstrap" in body.lower()


def test_admin_dashboard_renders_kpi_cards(client):
    """대시보드 응답에 KPI 카드 구조(card-stat)가 렌더링되어야 한다."""
    resp = client.get("/admin/")
    body = resp.data.decode("utf-8")
    assert "card" in body
    assert "대시보드" in body
