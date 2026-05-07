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


def test_issue_calls_stdout_write_and_flush(client, monkeypatch):
    events = {"writes": 0, "flushed": False}

    class _Stdout:
        def write(self, _text):
            events["writes"] += 1
            return 0

        def flush(self):
            events["flushed"] = True

    monkeypatch.setattr("src.auth.diagnostic_token.sys.stdout", _Stdout())
    monkeypatch.setattr("src.auth.diagnostic_token.secrets.token_urlsafe", lambda _n: "flush-token")

    resp = client.get("/auth/diagnostic-token/issue?format=json")
    assert resp.status_code == 200
    assert events["writes"] >= 3
    assert events["flushed"] is True

