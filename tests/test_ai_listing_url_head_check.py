"""tests/test_ai_listing_url_head_check.py — URL HEAD 검증 테스트."""
from __future__ import annotations

import json
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("AI_LISTING_ENABLED", "1")
    monkeypatch.setenv("AI_LISTING_VISION_PROVIDER", "mock")
    monkeypatch.setenv("AI_LISTING_URL_HEAD_CHECK", "1")
    from src.order_webhook import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def _mock_analysis():
    return {
        "category": "패션",
        "keywords": ["티셔츠"],
        "estimated_price_range": {"min": 10000, "max": 20000},
        "_prompt_version": "v2_explicit_fields",
        "_debug": {},
    }


def test_rejects_404_page_url(client):
    with (
        mock.patch("src.ai_listing.url_scraper.head_check_url", return_value={"ok": False, "status": 404, "error": "HTTP 404"}),
    ):
        resp = client.post(
            "/api/ai-listing/analyze",
            data=json.dumps({"page_url": "https://example.com/not-found", "language": "kr"}),
            content_type="application/json",
        )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "HTTP 404" in data["error"]


def test_allows_200_page_url(client):
    scrape_data = {
        "_http_status": 200,
        "_response_size": 1234,
        "_json_ld": [],
        "_og_tags": {},
        "_meta_description": "",
        "_cache_hit": False,
        "images": [],
        "_scraped": True,
    }
    with (
        mock.patch("src.ai_listing.url_scraper.head_check_url", return_value={"ok": True, "status": 200, "error": None}),
        mock.patch("src.ai_listing.url_scraper.scrape_product_page", return_value=scrape_data),
        mock.patch("src.ai_listing.analyzer.analyze_image", return_value=_mock_analysis()),
    ):
        resp = client.post(
            "/api/ai-listing/analyze",
            data=json.dumps({"page_url": "https://example.com/product", "language": "kr"}),
            content_type="application/json",
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
