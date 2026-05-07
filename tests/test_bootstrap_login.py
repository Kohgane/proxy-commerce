from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _DummyStore:
    def __init__(self):
        self.by_email = {}
        self.by_id = {}

    def find_by_email(self, email: str):
        return self.by_email.get((email or "").lower())

    def find_by_id(self, user_id: str):
        return self.by_id.get(user_id)

    def create(self, user):
        self.by_email[(user.email or "").lower()] = user
        self.by_id[user.user_id] = user
        return user

    def update(self, user):
        self.by_email[(user.email or "").lower()] = user
        self.by_id[user.user_id] = user

    def link_social(self, user_id: str, provider_data: dict):
        user = self.by_id.get(user_id)
        if user is not None:
            user.social_accounts.append(provider_data)


@pytest.fixture
def client(monkeypatch):
    store = _DummyStore()
    monkeypatch.setattr("src.auth.user_store.get_store", lambda: store)

    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-secret-bootstrap"
    with app.test_client() as c:
        yield c


def test_bootstrap_login_success_sets_admin_session(client, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", "token-123")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    resp = client.get("/auth/bootstrap?token=token-123&email=admin@example.com")

    assert resp.status_code in (302, 301)
    assert resp.headers["Location"].endswith("/admin/diagnostics")
    with client.session_transaction() as sess:
        assert sess["user_role"] == "admin"
        assert sess["user_email"] == "admin@example.com"


def test_bootstrap_login_invalid_token_returns_401(client, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", "token-123")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    resp = client.get("/auth/bootstrap?token=wrong&email=admin@example.com")

    assert resp.status_code == 401
    assert resp.get_json()["error"] == "유효하지 않은 토큰"


def test_bootstrap_login_requires_admin_email(client, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", "token-123")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    resp = client.get("/auth/bootstrap?token=token-123&email=seller@example.com")

    assert resp.status_code == 403
    assert "ADMIN_EMAILS" in resp.get_json()["hint"]


def test_bootstrap_login_returns_503_when_token_missing(client, monkeypatch):
    monkeypatch.delenv("ADMIN_BOOTSTRAP_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    resp = client.get("/auth/bootstrap?token=token-123&email=admin@example.com")

    assert resp.status_code == 503
    assert "ADMIN_BOOTSTRAP_TOKEN" in resp.get_json()["error"]
