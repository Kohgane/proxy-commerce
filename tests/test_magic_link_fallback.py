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
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MAGIC_LINK_TOKENS_PATH", str(tmp_path / "magic-link.jsonl"))
    monkeypatch.setenv("BASE_URL", "https://kohganepercentiii.com")
    monkeypatch.setattr("src.auth.user_store.get_store", lambda: _DummyStore())
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_resend_failure_admin_email_renders_fallback(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setattr("src.messaging.resend_adapter.send_email", lambda **kwargs: False)

    resp = client.post("/auth/magic-link", data={"email": "admin@example.com"})

    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "이메일 발송 실패" in html
    assert "/auth/magic-link/verify?token=" in html


def test_resend_failure_normal_email_no_fallback(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setattr("src.messaging.resend_adapter.send_email", lambda **kwargs: False)

    resp = client.post("/auth/magic-link", data={"email": "seller@example.com"})

    assert resp.status_code in (301, 302)
    assert "/auth/magic-link" in resp.headers["Location"]
