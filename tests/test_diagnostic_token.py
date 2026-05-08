from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://kohganepercentiii.com")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", "bootstrap-secret")

    from src.order_webhook import app
    import src.auth.diagnostic_token as diagnostic_token

    diagnostic_token._used_nonces.clear()
    diagnostic_token._issued_nonces.clear()
    diagnostic_token._issue_events.clear()
    diagnostic_token._redeem_events.clear()

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_issue_then_redeem_success(client, monkeypatch):
    c = client
    monkeypatch.setattr("src.auth.diagnostic_token.secrets.token_urlsafe", lambda n: "nonce-1")
    monkeypatch.setattr("src.auth.diagnostic_token.time.time", lambda: 1_700_000_000)
    from src.auth import diagnostic_token
    token = diagnostic_token._sign_payload({"v": 1, "exp": 1_700_000_600, "nonce": "nonce-1"})

    issue = c.get("/auth/diagnostic-token/issue")
    redeem = c.get(f"/auth/diagnostic-token/redeem?token={token}")

    assert issue.status_code == 200
    assert redeem.status_code in (301, 302)
    assert redeem.headers["Location"].endswith("/admin/diagnostics")
    with c.session_transaction() as sess:
        assert sess["user_role"] == "admin"
        assert sess["user_email"] == "admin@example.com"


def test_redeem_rejects_reuse(client, monkeypatch):
    c = client
    monkeypatch.setattr("src.auth.diagnostic_token.secrets.token_urlsafe", lambda n: "nonce-2")
    monkeypatch.setattr("src.auth.diagnostic_token.time.time", lambda: 1_700_000_000)
    from src.auth import diagnostic_token
    token = diagnostic_token._sign_payload({"v": 1, "exp": 1_700_000_600, "nonce": "nonce-2"})

    c.get("/auth/diagnostic-token/issue")
    first = c.get(f"/auth/diagnostic-token/redeem?token={token}")
    second = c.get(f"/auth/diagnostic-token/redeem?token={token}")

    assert first.status_code in (301, 302)
    assert second.status_code == 401


def test_redeem_rejects_expired_token(client, monkeypatch):
    c = client
    monkeypatch.setattr("src.auth.diagnostic_token.time.time", lambda: 1_700_000_000)
    from src.auth import diagnostic_token
    token = diagnostic_token._sign_payload({"v": 1, "exp": 1_699_999_999, "nonce": "expired"})

    resp = c.get(f"/auth/diagnostic-token/redeem?token={token}")

    assert resp.status_code == 401


def test_admin_emails_required(client, monkeypatch):
    c = client
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.setattr("src.auth.diagnostic_token.time.time", lambda: 1_700_000_000)
    from src.auth import diagnostic_token
    token = diagnostic_token._sign_payload({"v": 1, "exp": 1_700_000_600, "nonce": "nonce-missing-admin"})

    issue = c.get("/auth/diagnostic-token/issue")
    redeem = c.get(f"/auth/diagnostic-token/redeem?token={token}")

    assert issue.status_code == 200
    assert redeem.status_code == 503
