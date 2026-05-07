from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-secret-key-for-oauth-promotion"
    with app.test_client() as c:
        yield c


class _DummyProvider:
    def __init__(self, user_info: dict):
        self._user_info = user_info

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        return {"access_token": "token"}

    def get_user_info(self, access_token: str) -> dict:
        return self._user_info


class _DummyStore:
    def __init__(self):
        self.by_provider = {}
        self.by_email = {}

    def find_by_provider(self, provider: str, provider_user_id: str):
        return self.by_provider.get((provider, provider_user_id))

    def find_by_email(self, email: str):
        return self.by_email.get((email or "").lower())

    def link_social(self, user_id: str, provider_data: dict) -> None:
        pass

    def create(self, user):
        provider = user.social_accounts[0]["provider"]
        provider_user_id = user.social_accounts[0]["provider_user_id"]
        self.by_provider[(provider, provider_user_id)] = user
        self.by_email[(user.email or "").lower()] = user
        return user

    def update(self, user):
        self.by_email[(user.email or "").lower()] = user
        pass

    def update_last_login(self, user_id: str):
        return None


@pytest.mark.parametrize(
    "provider,user_info",
    [
        ("google", {"provider_user_id": "g-1", "email": "admin@example.com", "name": "Admin G", "avatar_url": ""}),
        ("kakao", {"provider_user_id": "k-1", "email": "admin@example.com", "name": "Admin K", "avatar_url": ""}),
        ("naver", {"provider_user_id": "n-1", "email": "admin@example.com", "name": "Admin N", "avatar_url": ""}),
    ],
)
def test_oauth_callback_promotes_admin_from_admin_emails(client, monkeypatch, provider, user_info):
    store = _DummyStore()
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setattr("src.auth.views._get_provider", lambda p: _DummyProvider(user_info))
    monkeypatch.setattr("src.auth.user_store.get_store", lambda: store)

    with client.session_transaction() as sess:
        sess[f"oauth_state_{provider}"] = "state-ok"
        sess[f"oauth_next_{provider}"] = "/seller/dashboard"

    resp = client.get(f"/auth/{provider}/callback?code=ok&state=state-ok")

    assert resp.status_code in (302, 301)
    with client.session_transaction() as sess:
        assert sess["user_role"] == "admin"


def test_oauth_callback_non_admin_email_stays_seller(client, monkeypatch):
    provider = "google"
    user_info = {"provider_user_id": "g-2", "email": "seller@example.com", "name": "Seller", "avatar_url": ""}
    store = _DummyStore()

    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setattr("src.auth.views._get_provider", lambda p: _DummyProvider(user_info))
    monkeypatch.setattr("src.auth.user_store.get_store", lambda: store)

    with client.session_transaction() as sess:
        sess[f"oauth_state_{provider}"] = "state-ok"

    resp = client.get(f"/auth/{provider}/callback?code=ok&state=state-ok")

    assert resp.status_code in (302, 301)
    with client.session_transaction() as sess:
        assert sess["user_role"] == "seller"


def test_oauth_callback_admin_emails_missing_defaults_seller(client, monkeypatch):
    provider = "google"
    user_info = {"provider_user_id": "g-3", "email": "admin@example.com", "name": "Admin", "avatar_url": ""}
    store = _DummyStore()

    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.setattr("src.auth.views._get_provider", lambda p: _DummyProvider(user_info))
    monkeypatch.setattr("src.auth.user_store.get_store", lambda: store)

    with client.session_transaction() as sess:
        sess[f"oauth_state_{provider}"] = "state-ok"

    resp = client.get(f"/auth/{provider}/callback?code=ok&state=state-ok")

    assert resp.status_code in (302, 301)
    with client.session_transaction() as sess:
        assert sess["user_role"] == "seller"


def test_oauth_callback_missing_email_forces_seller_and_warning(client, monkeypatch):
    provider = "kakao"
    user_info = {"provider_user_id": "k-2", "email": "", "name": "No Email", "avatar_url": ""}
    store = _DummyStore()

    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setattr("src.auth.views._get_provider", lambda p: _DummyProvider(user_info))
    monkeypatch.setattr("src.auth.user_store.get_store", lambda: store)

    with client.session_transaction() as sess:
        sess[f"oauth_state_{provider}"] = "state-ok"

    resp = client.get(f"/auth/{provider}/callback?code=ok&state=state-ok")

    assert resp.status_code in (302, 301)
    with client.session_transaction() as sess:
        assert sess["user_role"] == "seller"
        flashes = sess.get("_flashes", [])
        assert any(cat == "warning" for cat, _ in flashes)
