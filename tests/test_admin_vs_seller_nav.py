from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import src.order_webhook as wh

    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


def test_seller_route_uses_seller_sidebar(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "admin-user"
        sess["user_role"] = "admin"
    resp = client.get("/seller/sourcing/watches")
    html = resp.get_data(as_text=True)
    assert "🛒 셀러 콘솔" in html
    assert "/seller/sourcing/watches" in html
    assert "/admin/products" not in html


def test_admin_route_uses_admin_sidebar(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "admin-user"
        sess["user_role"] = "admin"
    resp = client.get("/admin/diagnostics")
    html = resp.get_data(as_text=True)
    assert "🛒 Admin" in html
    assert "/admin/products" in html
    assert "🛒 셀러 콘솔" not in html
