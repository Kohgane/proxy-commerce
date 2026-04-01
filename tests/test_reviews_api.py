"""tests/test_reviews_api.py — 리뷰 API 엔드포인트 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def api_client(mock_env, monkeypatch):
    """reviews_bp가 등록된 Flask 테스트 클라이언트."""
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    with wh.app.test_client() as c:
        yield c


SAMPLE_REVIEWS = [
    {
        "review_id": "r001",
        "order_id": "ORD-1",
        "product_sku": "SKU-A",
        "rating": 5,
        "text": "매우 좋습니다",
        "platform": "shopify",
        "customer_email": "a@a.com",
        "status": "approved",
        "created_at": "2026-03-01T10:00:00+00:00",
    },
    {
        "review_id": "r002",
        "order_id": "ORD-2",
        "product_sku": "SKU-B",
        "rating": 2,
        "text": "별로예요",
        "platform": "woocommerce",
        "customer_email": "b@b.com",
        "status": "pending",
        "created_at": "2026-03-10T10:00:00+00:00",
    },
]


class TestListReviews:
    def test_returns_200(self, api_client):
        """GET /api/reviews는 200을 반환해야 한다."""
        with patch('src.reviews.collector.ReviewCollector.get_reviews', return_value=SAMPLE_REVIEWS):
            resp = api_client.get('/api/reviews')
        assert resp.status_code == 200

    def test_returns_review_list(self, api_client):
        """리뷰 목록이 reviews 키로 반환되어야 한다."""
        with patch('src.reviews.collector.ReviewCollector.get_reviews', return_value=SAMPLE_REVIEWS):
            resp = api_client.get('/api/reviews')
        data = resp.get_json()
        assert "reviews" in data
        assert data["count"] == 2

    def test_rating_filter(self, api_client):
        """rating 쿼리 파라미터로 필터링되어야 한다."""
        with patch('src.reviews.collector.ReviewCollector.get_reviews', return_value=[SAMPLE_REVIEWS[0]]):
            resp = api_client.get('/api/reviews?rating=5')
        assert resp.status_code == 200

    def test_invalid_rating_returns_400(self, api_client):
        """유효하지 않은 rating은 400을 반환해야 한다."""
        with patch('src.reviews.collector.ReviewCollector.get_reviews', return_value=[]):
            resp = api_client.get('/api/reviews?rating=abc')
        assert resp.status_code == 400

    def test_status_filter(self, api_client):
        """status 쿼리 파라미터로 필터링되어야 한다."""
        with patch('src.reviews.collector.ReviewCollector.get_reviews', return_value=[SAMPLE_REVIEWS[0]]):
            resp = api_client.get('/api/reviews?status=approved')
        assert resp.status_code == 200


class TestReviewSummary:
    def test_returns_200(self, api_client):
        """GET /api/reviews/summary는 200을 반환해야 한다."""
        summary = {
            "period_days": 30,
            "total_reviews": 2,
            "average_rating": 3.5,
            "by_rating": {1: 0, 2: 1, 3: 0, 4: 0, 5: 1},
            "negative_count": 1,
            "top_keywords": [],
            "avg_by_sku": {},
        }
        with patch('src.reviews.collector.ReviewCollector.get_reviews', return_value=SAMPLE_REVIEWS):
            with patch('src.reviews.analyzer.ReviewAnalyzer.generate_review_summary', return_value=summary):
                resp = api_client.get('/api/reviews/summary')
        assert resp.status_code == 200

    def test_summary_has_required_keys(self, api_client):
        """요약 응답에 필수 키가 있어야 한다."""
        with patch('src.reviews.collector.ReviewCollector.get_reviews', return_value=[]):
            with patch('src.reviews.analyzer.ReviewAnalyzer.generate_review_summary', return_value={
                "period_days": 30,
                "total_reviews": 0,
                "average_rating": 0.0,
                "by_rating": {},
                "negative_count": 0,
                "top_keywords": [],
                "avg_by_sku": {},
            }):
                resp = api_client.get('/api/reviews/summary')
        data = resp.get_json()
        assert "total_reviews" in data


class TestUpdateReviewStatus:
    def test_approve_success(self, api_client):
        """리뷰 승인 PATCH가 성공해야 한다."""
        with patch('src.reviews.collector.ReviewCollector.update_status', return_value=True):
            resp = api_client.patch(
                '/api/reviews/r001/status',
                json={"status": "approved"},
                content_type='application/json',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("ok") is True

    def test_invalid_status_returns_400(self, api_client):
        """유효하지 않은 상태는 400을 반환해야 한다."""
        resp = api_client.patch(
            '/api/reviews/r001/status',
            json={"status": "invalid"},
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_not_found_returns_404(self, api_client):
        """리뷰가 없으면 404를 반환해야 한다."""
        with patch('src.reviews.collector.ReviewCollector.update_status', return_value=False):
            resp = api_client.patch(
                '/api/reviews/nonexistent/status',
                json={"status": "approved"},
                content_type='application/json',
            )
        assert resp.status_code == 404
