from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", "bootstrap-secret")
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_diagnostics_banner_when_reveal_on(client, monkeypatch):
    monkeypatch.setenv("DIAGNOSTIC_REVEAL", "1")
    with client.session_transaction() as sess:
        sess["user_id"] = "admin-1"
        sess["user_role"] = "admin"
    html = client.get("/admin/diagnostics").get_data(as_text=True)
    assert "비상 진입 모드 ON" in html


def test_diagnostic_issue_page_banner_when_reveal_on(client, monkeypatch):
    monkeypatch.setenv("DIAGNOSTIC_REVEAL", "1")
    html = client.get("/auth/diagnostic-token/issue?format=html").get_data(as_text=True)
    assert "비상 진입 모드 ON" in html
