from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-secret-key-for-whoami"
    with app.test_client() as c:
        yield c


def test_whoami_logged_out(client):
    resp = client.get("/auth/whoami")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["logged_in"] is False
    assert data["is_admin"] is False


def test_whoami_logged_in(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "u-1"
        sess["user_email"] = "admin@example.com"
        sess["user_role"] = "admin"
        sess["user_name"] = "관리자"

    resp = client.get("/auth/whoami")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["logged_in"] is True
    assert data["user_id"] == "u-1"
    assert data["user_email"] == "admin@example.com"
    assert data["user_role"] == "admin"
    assert data["user_name"] == "관리자"
    assert data["is_admin"] is True


def test_seller_header_logged_out_shows_login_links(client):
    resp = client.get("/seller/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "로그인" in html
    assert "이메일 로그인" in html


def test_seller_header_logged_in_shows_email_and_badge(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "u-2"
        sess["user_email"] = "seller@example.com"
        sess["user_role"] = "seller"

    resp = client.get("/seller/dashboard")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "seller@example.com" in html
    assert "셀러" in html
    assert "로그아웃" in html


def test_admin_sidebar_menu_only_for_admin(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "u-3"
        sess["user_role"] = "seller"
    resp = client.get("/seller/dashboard")
    assert "관리자 패널" not in resp.get_data(as_text=True)

    with client.session_transaction() as sess:
        sess["user_id"] = "u-4"
        sess["user_role"] = "admin"
    resp2 = client.get("/seller/dashboard")
    assert "관리자 패널" in resp2.get_data(as_text=True)


def test_pricing_rules_create_requires_login(client):
    resp = client.post("/seller/pricing/rules", json={"name": "테스트"})
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["error"] == "로그인이 필요합니다."
    assert data["login_url"] == "/auth/login"
