from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ROOT_REDIRECT", "landing")
    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-landing-footer-privacy"
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize("path", ["/", "/auth/login", "/seller/listing/ai-create"])
def test_pages_have_privacy_link(client, path):
    html = client.get(path).get_data(as_text=True)
    assert 'href="/privacy"' in html
    assert 'href="/terms"' in html


def test_landing_has_privacy_policy_meta_link(client):
    html = client.get("/").get_data(as_text=True)
    assert '<link rel="privacy-policy" href="/privacy">' in html


def test_privacy_page_contains_enough_korean_content(client):
    html = client.get("/privacy").get_data(as_text=True)
    korean_chars = [ch for ch in html if "\uac00" <= ch <= "\ud7a3"]
    assert len(korean_chars) >= 200
