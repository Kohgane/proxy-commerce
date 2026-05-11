from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize("path", ["/", "/seller/dashboard", "/admin/", "/seller/orders/auto", "/not-found-phase146"])
def test_header_branch_logged_out_shows_guest_actions(client, path):
    html = client.get(path, follow_redirects=True).get_data(as_text=True)
    assert "OAuth 로그인" in html
    assert "이메일 로그인" in html


@pytest.mark.parametrize("path", ["/", "/seller/dashboard", "/admin/", "/seller/orders/auto", "/not-found-phase146"])
def test_header_branch_logged_in_shows_user_menu(client, path):
    with client.session_transaction() as sess:
        sess["user_id"] = "u-phase146"
        sess["user_email"] = "seller@example.com"
        sess["user_role"] = "seller"

    html = client.get(path, follow_redirects=True).get_data(as_text=True)
    assert "OAuth 로그인" not in html
    assert "이메일 로그인" not in html
    assert "로그아웃" in html
