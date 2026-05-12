from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _DummyProvider:
    is_configured = True

    def get_authorize_url(self, state: str, redirect_uri: str) -> str:
        return "https://example.com/oauth"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        return {"access_token": "token"}

    def get_user_info(self, access_token: str) -> dict:
        return {
            "provider_user_id": "kakao-user-1",
            "email": "seller@example.com",
            "name": "Seller",
            "avatar_url": "",
        }


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-kakao-callback-redirect"
    with app.test_client() as c:
        yield c


def test_kakao_callback_redirects_to_dashboard_and_sets_session(client, monkeypatch):
    monkeypatch.setattr("src.auth.views._get_provider", lambda provider: _DummyProvider())
    with client.session_transaction() as sess:
        sess["oauth_state_kakao"] = "ok-state"
        sess["oauth_next_kakao"] = "/seller/dashboard"

    resp = client.get("/auth/kakao/callback?code=ok-code&state=ok-state")
    assert resp.status_code in (301, 302)
    assert resp.headers.get("Location", "").endswith("/seller/dashboard")
    assert "session=" in resp.headers.get("Set-Cookie", "")
