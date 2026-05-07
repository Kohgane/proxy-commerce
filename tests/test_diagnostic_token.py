from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch, tmp_path):
    token_path = tmp_path / "diagnostic_tokens.jsonl"
    monkeypatch.setenv("DIAGNOSTIC_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("BASE_URL", "https://kohganepercentiii.com")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    from src.order_webhook import app
    import src.auth.diagnostic_token as diagnostic_token

    diagnostic_token._FILE = token_path
    diagnostic_token._FILE.parent.mkdir(parents=True, exist_ok=True)

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, token_path


def test_issue_then_redeem_success(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr("src.auth.diagnostic_token.secrets.token_urlsafe", lambda n: "raw-token-1")

    issue = c.get("/auth/diagnostic-token/issue")
    redeem = c.get("/auth/diagnostic-token/redeem?token=raw-token-1")

    assert issue.status_code == 200
    assert redeem.status_code in (301, 302)
    assert redeem.headers["Location"].endswith("/admin/diagnostics")
    with c.session_transaction() as sess:
        assert sess["user_role"] == "admin"
        assert sess["user_email"] == "admin@example.com"


def test_redeem_rejects_reuse(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr("src.auth.diagnostic_token.secrets.token_urlsafe", lambda n: "raw-token-2")

    c.get("/auth/diagnostic-token/issue")
    first = c.get("/auth/diagnostic-token/redeem?token=raw-token-2")
    second = c.get("/auth/diagnostic-token/redeem?token=raw-token-2")

    assert first.status_code in (301, 302)
    assert second.status_code == 401


def test_redeem_rejects_expired_token(client):
    c, token_path = client
    token_hash = hashlib.sha256("expired-token".encode()).hexdigest()
    token_path.write_text(
        json.dumps(
            {
                "token_hash": token_hash,
                "expires_at": int(time.time()) - 1,
                "used": False,
                "issued_at": datetime.now(tz=timezone.utc).isoformat(),
                "issuer_ip": "127.0.0.1",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    resp = c.get("/auth/diagnostic-token/redeem?token=expired-token")

    assert resp.status_code == 401


def test_admin_emails_required(client, monkeypatch):
    c, _ = client
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)

    issue = c.get("/auth/diagnostic-token/issue")
    redeem = c.get("/auth/diagnostic-token/redeem?token=any")

    assert issue.status_code == 200
    assert redeem.status_code == 503
