"""tests/test_ai_listing_force_refresh.py — 캐시 무시 동작 테스트."""
from __future__ import annotations

import json
import os
import sys
import time
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("AI_LISTING_ENABLED", "1")
    monkeypatch.setenv("AI_LISTING_VISION_PROVIDER", "mock")
    monkeypatch.setenv("AI_LISTING_FORCE_REFRESH_ALLOWED", "1")
    from src.order_webhook import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def test_force_refresh_query_is_forwarded(client):
    scrape_data = {"_http_status": 200, "_scraped": True, "_cache_hit": False, "images": []}
    analysis = {
        "category": "패션",
        "keywords": ["티셔츠"],
        "estimated_price_range": {"min": 10000, "max": 20000},
        "_prompt_version": "v2_explicit_fields",
        "_debug": {},
    }
    with (
        mock.patch("src.ai_listing.url_scraper.head_check_url", return_value={"ok": True, "status": 200, "error": None}),
        mock.patch("src.ai_listing.url_scraper.scrape_product_page", return_value=scrape_data) as m_scrape,
        mock.patch("src.ai_listing.analyzer.analyze_image", return_value=analysis) as m_analyze,
    ):
        resp = client.post(
            "/api/ai-listing/analyze?force_refresh=1",
            data=json.dumps({"page_url": "https://example.com/p/1", "language": "kr"}),
            content_type="application/json",
        )

    assert resp.status_code == 200
    assert m_scrape.call_args.kwargs["force_refresh"] is True
    assert m_analyze.call_args.kwargs["force_refresh"] is True


def test_force_refresh_replaces_analyzer_and_scraper_cache(monkeypatch):
    monkeypatch.setenv("AI_LISTING_VISION_PROVIDER", "mock")
    from src.ai_listing import analyzer
    from src.ai_listing import url_scraper
    from src.ai_listing.analyzer import _make_analysis_cache_key

    analyzer._analysis_cache.clear()
    url_scraper._scraper_cache.clear()

    image_url = "https://example.com/image.jpg"
    page_url = "https://example.com/product"
    image_hash = analyzer._compute_image_hash(image_url=image_url)
    url_hash = url_scraper._url_hash(page_url)

    # Phase 151.1: 캐시 키는 composite 형식 (phase:prompt:url:img)
    cache_key = _make_analysis_cache_key(image_hash, "v2_explicit_fields", page_url=page_url)
    analyzer._analysis_cache[cache_key] = {"result": {"category": "old"}, "_cached_at": time.time()}
    url_scraper._scraper_cache[url_hash] = {"result": {"title": "old", "_cache_hit": False}, "_cached_at": time.time()}

    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><head><title>new title</title></head><body></body></html>"
    mock_resp.content = mock_resp.text.encode("utf-8")

    with (
        mock.patch("requests.get", return_value=mock_resp),
        mock.patch("src.ai_listing.url_scraper.head_check_url", return_value={"ok": True, "status": 200, "error": None}),
    ):
        scraped = url_scraper.scrape_product_page(page_url, force_refresh=True)
        analyzed = analyzer.analyze_image(image_url=image_url, page_url=page_url, force_refresh=True)

    assert scraped.get("_cache_hit") is False
    assert analyzed.get("_analysis_cache_hit") is False
    # 이전 캐시 항목이 삭제되고 새 항목이 저장됨
    assert cache_key not in analyzer._analysis_cache or analyzer._analysis_cache.get(cache_key, {}).get("result", {}).get("category") != "old"
