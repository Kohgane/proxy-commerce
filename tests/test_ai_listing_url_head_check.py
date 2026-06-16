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


# ──────────────────────────────────────────────────────────
# head_check_url 단위 테스트 — 봇 차단 사이트 GET 폴백
# ──────────────────────────────────────────────────────────


class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code

    def close(self):
        pass


def test_head_check_falls_back_to_get_when_head_blocked():
    """HEAD가 500(봇 차단)이어도 GET이 200이면 접근 가능으로 판정."""
    from src.ai_listing import url_scraper

    with (
        mock.patch.object(url_scraper, "_HEAD_GET_FALLBACK", True),
        mock.patch("requests.head", return_value=_Resp(500)),
        mock.patch("requests.get", return_value=_Resp(200)) as mget,
    ):
        result = url_scraper.head_check_url("https://www.yoshidakaban.com/ko/product/102501.html")

    assert result["ok"] is True
    assert result["status"] == 200
    mget.assert_called_once()


def test_head_check_ok_on_head_200_without_get():
    """HEAD가 바로 200이면 GET 폴백 없이 통과."""
    from src.ai_listing import url_scraper

    with (
        mock.patch("requests.head", return_value=_Resp(200)),
        mock.patch("requests.get") as mget,
    ):
        result = url_scraper.head_check_url("https://example.com/product")

    assert result["ok"] is True
    assert result["status"] == 200
    mget.assert_not_called()


def test_head_check_fails_when_both_blocked():
    """HEAD/GET 모두 404면 정직하게 실패."""
    from src.ai_listing import url_scraper

    with (
        mock.patch.object(url_scraper, "_HEAD_GET_FALLBACK", True),
        mock.patch("requests.head", return_value=_Resp(404)),
        mock.patch("requests.get", return_value=_Resp(404)),
    ):
        result = url_scraper.head_check_url("https://example.com/missing")

    assert result["ok"] is False
    assert result["status"] == 404
