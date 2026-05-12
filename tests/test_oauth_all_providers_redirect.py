from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _DummyProvider:
    is_configured = True

    def __init__(self, provider: str):
        self.provider = provider

    def get_authorize_url(self, state: str, redirect_uri: str) -> str:
        return "https://example.com/oauth"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        return {"access_token": "token"}

    def get_user_info(self, access_token: str) -> dict:
        return {
            "provider_user_id": f"{self.provider}-user",
            "email": f"{self.provider}@example.com",
            "name": self.provider,
            "avatar_url": "",
        }


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-oauth-all-providers"
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize("provider", ["google", "naver", "kakao"])
def test_oauth_callback_redirects_for_all_providers(client, monkeypatch, provider):
    monkeypatch.setattr("src.auth.views._get_provider", lambda p: _DummyProvider(provider))
    with client.session_transaction() as sess:
        sess[f"oauth_state_{provider}"] = "ok-state"
        sess[f"oauth_next_{provider}"] = "/seller/dashboard"

    resp = client.get(f"/auth/{provider}/callback?code=ok-code&state=ok-state")
    assert resp.status_code in (301, 302)
    assert resp.headers.get("Location", "").endswith("/seller/dashboard")
