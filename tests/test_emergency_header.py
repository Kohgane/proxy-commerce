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


def test_emergency_button_visible_when_reveal_enabled(client, monkeypatch):
    monkeypatch.setenv("DIAGNOSTIC_REVEAL", "1")
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "🆘 비상 진입 (운영자)" in html
    assert "/auth/diagnostic-token/issue?reveal_safe=1&format=html" in html


def test_emergency_button_hidden_when_reveal_disabled(client, monkeypatch):
    monkeypatch.setenv("DIAGNOSTIC_REVEAL", "0")
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "🆘 비상 진입 (운영자)" not in html
