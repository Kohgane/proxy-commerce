from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

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
    tokens_path = tmp_path / "magic-link.jsonl"
    monkeypatch.setenv("MAGIC_LINK_TOKENS_PATH", str(tokens_path))
    monkeypatch.setenv("BASE_URL", "https://kohganepercentiii.com")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)

    store = _DummyStore()
    monkeypatch.setattr("src.auth.user_store.get_store", lambda: store)

    sent = {}

    def _fake_send_email(*, to, subject, html, text, **kwargs):
        sent["to"] = to
        sent["subject"] = subject
        sent["html"] = html
        sent["text"] = text
        return True

    monkeypatch.setattr("src.messaging.resend_adapter.send_email", _fake_send_email)

    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-secret-magic-link"
    with app.test_client() as c:
        yield c, tokens_path, store, sent


def _extract_verify_path(sent: dict) -> str:
    text = sent["text"]
    link = text.split(": ", 1)[1]
    parsed = urlparse(link)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _read_records(tokens_path):
    return [json.loads(line) for line in tokens_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_magic_link_token_created_and_hashed(client):
    client_obj, tokens_path, _, sent = client

    resp = client_obj.post("/auth/magic-link", data={"email": "seller@example.com"})

    assert resp.status_code in (302, 301)
    assert tokens_path.exists()
    records = _read_records(tokens_path)
    assert len(records) == 1
    assert records[0]["email"] == "seller@example.com"
    assert records[0]["token_hash"]
    assert "/auth/magic-link/verify?" in sent["text"]


def test_magic_link_verify_success(client):
    client_obj, _, _, sent = client
    client_obj.post("/auth/magic-link", data={"email": "seller@example.com", "next": "/seller/pricing/rules"})

    resp = client_obj.get(_extract_verify_path(sent))

    assert resp.status_code in (302, 301)
    assert resp.headers["Location"].endswith("/seller/pricing/rules")
    with client_obj.session_transaction() as sess:
        assert sess["user_email"] == "seller@example.com"
        assert sess["user_role"] == "seller"


def test_magic_link_expired_token_rejected(client):
    client_obj, tokens_path, _, sent = client
    client_obj.post("/auth/magic-link", data={"email": "seller@example.com"})

    records = _read_records(tokens_path)
    records[0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()
    tokens_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")

    resp = client_obj.get(_extract_verify_path(sent))

    assert resp.status_code in (302, 301)
    assert "/auth/magic-link" in resp.headers["Location"]


def test_magic_link_cannot_be_reused(client):
    client_obj, _, _, sent = client
    client_obj.post("/auth/magic-link", data={"email": "seller@example.com"})
    verify_path = _extract_verify_path(sent)

    first = client_obj.get(verify_path)
    second = client_obj.get(verify_path)

    assert first.status_code in (302, 301)
    assert second.status_code in (302, 301)
    assert "/auth/magic-link" in second.headers["Location"]


def test_magic_link_invalid_token_rejected(client):
    client_obj, _, _, _ = client

    resp = client_obj.get("/auth/magic-link/verify?token=bad-token&email=seller@example.com")

    assert resp.status_code in (302, 301)
    assert "/auth/magic-link" in resp.headers["Location"]


def test_magic_link_admin_email_promotes_admin(client, monkeypatch):
    client_obj, _, _, sent = client
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    client_obj.post("/auth/magic-link", data={"email": "admin@example.com"})

    resp = client_obj.get(_extract_verify_path(sent))

    assert resp.status_code in (302, 301)
    with client_obj.session_transaction() as sess:
        assert sess["user_role"] == "admin"
        assert sess["user_email"] == "admin@example.com"
