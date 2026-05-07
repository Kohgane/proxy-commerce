from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_bootstrap_placeholder_token_returns_400_hint(client, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", "real-token")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    resp = client.get("/auth/bootstrap?token=<ADMIN_BOOTSTRAP_TOKEN>&email=admin@example.com")

    assert resp.status_code == 400
    data = resp.get_json()
    assert "placeholder" in data["error"]
    assert "ADMIN_BOOTSTRAP_TOKEN" in data["hint"]


def test_bootstrap_double_prefix_returns_400_hint(client, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", "real-token")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    resp = client.get("/auth/bootstrap?token=/auth/bootstrap?token=abc&email=admin@example.com")

    assert resp.status_code == 400
    data = resp.get_json()
    assert "URL 일부" in data["error"]
    assert "토큰 값만" in data["hint"]
