"""tests/test_ai_listing_routes_v2.py — v2 호출 체인 검증."""
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
    monkeypatch.setenv("AI_LISTING_PROMPT_VERSION", "v2_explicit_fields")
    from src.order_webhook import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def test_analyze_route_uses_scraper_and_v2_prompt(client):
    scrape_output = {
        "_http_status": 200,
        "_response_size": 512,
        "_json_ld": [{"@type": "Product"}],
        "_og_tags": {"title": "상품"},
        "_meta_description": "설명",
        "_cache_hit": False,
        "_scraped": True,
        "images": ["https://example.com/img.jpg"],
    }
    analysis = {
        "category": "패션",
        "brand": "브랜드X",
        "keywords": ["티셔츠"],
        "estimated_price_range": {"min": 15000, "max": 29000},
        "_scraped": True,
        "_brand_source": "scraping",
        "_price_source": "scraping",
        "_prompt_version": "v2_explicit_fields",
        "_debug": {
            "http_status": 200,
            "response_size": 512,
            "json_ld": [{"@type": "Product"}],
            "og_tags": {"title": "상품"},
            "meta_description": "설명",
            "image_urls": ["https://example.com/img.jpg"],
            "scraper_cache_hit": False,
        },
    }

    with (
        mock.patch("src.ai_listing.url_scraper.head_check_url", return_value={"ok": True, "status": 200, "error": None}),
        mock.patch("src.ai_listing.url_scraper.scrape_product_page", return_value=scrape_output) as m_scrape,
        mock.patch("src.ai_listing.analyzer.analyze_image", return_value=analysis) as m_analyze,
    ):
        resp = client.post(
            "/api/ai-listing/analyze",
            data=json.dumps({"page_url": "https://example.com/product", "language": "kr"}),
            content_type="application/json",
        )

    assert resp.status_code == 200
    assert m_scrape.called
    assert m_analyze.call_args.kwargs["prompt_version"] == "v2_explicit_fields"
    data = resp.get_json()
    assert "confidence_badges" in data
    assert "brand" in data["confidence_badges"]
    assert data["debug_panel"]["prompt_version"] == "v2_explicit_fields"
