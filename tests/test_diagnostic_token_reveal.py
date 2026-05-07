from __future__ import annotations

import os
import sys

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
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_reveal_html_when_env_enabled(client, monkeypatch):
    monkeypatch.setenv("DIAGNOSTIC_REVEAL", "1")
    monkeypatch.setattr("src.auth.diagnostic_token.secrets.token_urlsafe", lambda _n: "reveal-token")
    resp = client.get("/auth/diagnostic-token/issue?format=html")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Admin 세션 시작" in html
    assert "reveal-token" in html


def test_json_only_when_reveal_disabled(client, monkeypatch):
    monkeypatch.setenv("DIAGNOSTIC_REVEAL", "0")
    monkeypatch.setattr("src.auth.diagnostic_token.secrets.token_urlsafe", lambda _n: "json-token")
    resp = client.get("/auth/diagnostic-token/issue?format=json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "log_keyword" in data
    assert "json-token" not in str(data)


def test_reveal_safe_without_admin_emails_does_not_reveal_url(client, monkeypatch):
    monkeypatch.setenv("DIAGNOSTIC_REVEAL", "0")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.setattr("src.auth.diagnostic_token.secrets.token_urlsafe", lambda _n: "safe-token")
    resp = client.get("/auth/diagnostic-token/issue?reveal_safe=1&format=html")
    assert resp.status_code == 200
    assert resp.is_json
    assert "safe-token" not in resp.get_data(as_text=True)

