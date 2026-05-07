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


def test_issue_triggers_telegram_alert(client, monkeypatch):
    captured = {}

    def _fake_send_telegram(message, urgency="info"):
        captured["message"] = message
        captured["urgency"] = urgency
        return True

    monkeypatch.setattr("src.notifications.telegram.send_telegram", _fake_send_telegram)
    client.get("/auth/diagnostic-token/issue?format=json")
    assert "Diagnostic Token 발급됨" in captured["message"]
    assert captured["urgency"] == "warning"

