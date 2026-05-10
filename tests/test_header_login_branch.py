from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_header_branch_logged_in_hides_guest_actions():
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_email"] = "seller@example.com"
            sess["user_role"] = "seller"
        html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "OAuth 로그인" not in html
    assert "로그아웃" in html


def test_header_branch_logged_out_shows_guest_actions():
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "OAuth 로그인" in html
    assert "이메일 로그인" in html
