from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-secret-legal"
    with app.test_client() as c:
        yield c


def test_privacy_page_returns_200_and_contains_korean_content(client):
    resp = client.get("/privacy")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "개인정보처리방침" in html
    assert "수집 정보" in html


def test_terms_page_returns_200_and_contains_korean_content(client):
    resp = client.get("/terms")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "이용약관" in html
    assert "사용자 책임" in html
