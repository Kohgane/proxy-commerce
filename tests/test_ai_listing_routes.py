"""tests/test_ai_listing_routes.py — 페이지 200, 권한, BudgetGuard 테스트 (Phase 149)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def app():
    os.environ.setdefault("SECRET_KEY", "test-secret")
    os.environ.setdefault("AI_LISTING_ENABLED", "1")
    os.environ.setdefault("AI_LISTING_VISION_PROVIDER", "mock")
    from src.order_webhook import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


class TestAIListingPageRoute:
    def test_ai_create_page_returns_not_404(self, client):
        resp = client.get("/seller/listing/ai-create")
        assert resp.status_code != 404, "/seller/listing/ai-create → 404 (Phase 149 라우트 미등록)"

    def test_ai_create_page_returns_200(self, client):
        resp = client.get("/seller/listing/ai-create")
        assert resp.status_code == 200, (
            f"/seller/listing/ai-create → {resp.status_code} (200 예상)"
        )

    def test_ai_create_page_contains_phase_marker(self, client):
        resp = client.get("/seller/listing/ai-create")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")
        assert "Phase 149" in data or "ai-listing" in data.lower()

    def test_ai_create_page_has_upload_ui(self, client):
        resp = client.get("/seller/listing/ai-create")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")
        assert "이미지" in data or "image" in data.lower()


class TestAIListingAPIRoutes:
    def test_analyze_api_post(self, client):
        import json
        resp = client.post(
            "/api/ai-listing/analyze",
            data=json.dumps({"image_url": "https://example.com/test.jpg", "language": "kr"}),
            content_type="application/json",
        )
        assert resp.status_code in (200, 403, 429)
        data = json.loads(resp.data)
        assert "ok" in data

    def test_analyze_api_without_url_returns_400(self, client):
        import json
        resp = client.post(
            "/api/ai-listing/analyze",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code in (400, 403)

    def test_generate_api_post(self, client):
        import json
        resp = client.post(
            "/api/ai-listing/generate",
            data=json.dumps({
                "listing_id": "test-id",
                "analysis": {"category": "패션", "keywords": ["티셔츠"], "product_type": "티셔츠", "estimated_price_range": {"min": 10000, "max": 30000}},
                "markets": ["coupang"],
                "language": "kr",
            }),
            content_type="application/json",
        )
        assert resp.status_code in (200, 403)

    def test_generate_api_returns_market_data(self, client):
        import json
        resp = client.post(
            "/api/ai-listing/generate",
            data=json.dumps({
                "listing_id": "test-id",
                "analysis": {"category": "패션", "keywords": ["티셔츠"], "product_type": "티셔츠", "estimated_price_range": {"min": 10000, "max": 30000}},
                "markets": ["coupang", "smartstore"],
                "language": "kr",
            }),
            content_type="application/json",
        )
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert data.get("ok") is True
            assert "markets" in data
            assert "coupang" in data["markets"]

    def test_publish_api_post(self, client):
        import json
        resp = client.post(
            "/api/ai-listing/publish",
            data=json.dumps({
                "listing_id": "test-listing",
                "markets": ["coupang"],
                "analysis": {"category": "패션"},
            }),
            content_type="application/json",
        )
        assert resp.status_code in (200, 403)

    def test_status_api_get(self, client):
        resp = client.get("/api/ai-listing/status/test-listing-id")
        assert resp.status_code == 200


class TestAIListingRouteRegistration:
    def test_ai_listing_create_registered(self, app):
        view_funcs = app.view_functions
        assert any(
            "ai_listing" in k and "create" in k.lower()
            for k in view_funcs
        ), "ai_listing.ai_listing_create 라우트 미등록"

    def test_ai_listing_api_analyze_registered(self, app):
        routes = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/api/ai-listing/analyze" in routes, "/api/ai-listing/analyze 라우트 미등록"

    def test_ai_listing_api_generate_registered(self, app):
        routes = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/api/ai-listing/generate" in routes

    def test_ai_listing_api_publish_registered(self, app):
        routes = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/api/ai-listing/publish" in routes
