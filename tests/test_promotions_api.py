"""tests/test_promotions_api.py — 프로모션 API 엔드포인트 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def api_client(mock_env, monkeypatch):
    """promotions_bp가 등록된 Flask 테스트 클라이언트."""
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    with wh.app.test_client() as c:
        yield c


SAMPLE_PROMOS = [
    {
        "promo_id": "P001",
        "name": "여름 할인",
        "type": "PERCENTAGE",
        "value": 10,
        "active": "1",
        "start_date": "2026-06-01T00:00:00",
        "end_date": "2026-06-30T23:59:59",
        "min_order_krw": 50000,
        "skus": "",
        "countries": "",
        "usage_count": 5,
        "total_discount_krw": 25000,
    }
]

SAMPLE_STATS = {
    "promo_id": "P001",
    "name": "여름 할인",
    "usage_count": 5,
    "total_discount_krw": 25000.0,
    "active": True,
}


class TestListPromotions:
    def test_returns_200(self, api_client):
        """GET /api/promotions는 200을 반환해야 한다."""
        with patch('src.promotions.engine.PromotionEngine.get_promotions', return_value=SAMPLE_PROMOS):
            resp = api_client.get('/api/promotions')
        assert resp.status_code == 200

    def test_returns_promotion_list(self, api_client):
        """프로모션 목록이 promotions 키로 반환되어야 한다."""
        with patch('src.promotions.engine.PromotionEngine.get_promotions', return_value=SAMPLE_PROMOS):
            resp = api_client.get('/api/promotions')
        data = resp.get_json()
        assert "promotions" in data
        assert data["count"] == 1

    def test_active_only_filter(self, api_client):
        """active_only=1 파라미터가 동작해야 한다."""
        with patch('src.promotions.engine.PromotionEngine.get_promotions', return_value=SAMPLE_PROMOS) as mock_get:
            resp = api_client.get('/api/promotions?active_only=1')
        assert resp.status_code == 200
        mock_get.assert_called_with(active_only=True)


class TestCreatePromotion:
    def test_create_success_returns_201(self, api_client):
        """POST /api/promotions 성공 시 201을 반환해야 한다."""
        new_promo = dict(SAMPLE_PROMOS[0])
        with patch('src.promotions.engine.PromotionEngine.create_promotion', return_value=new_promo):
            resp = api_client.post(
                '/api/promotions',
                json={"name": "여름 할인", "type": "PERCENTAGE", "value": 10},
                content_type='application/json',
            )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data.get("ok") is True

    def test_create_invalid_returns_400(self, api_client):
        """유효하지 않은 데이터 시 400을 반환해야 한다."""
        with patch('src.promotions.engine.PromotionEngine.create_promotion',
                   side_effect=ValueError("Invalid type")):
            resp = api_client.post(
                '/api/promotions',
                json={"name": "X", "type": "INVALID"},
                content_type='application/json',
            )
        assert resp.status_code == 400


class TestUpdatePromotion:
    def test_update_success(self, api_client):
        """PATCH /api/promotions/<id> 성공 시 ok=True를 반환해야 한다."""
        with patch('src.promotions.engine.PromotionEngine.update_promotion', return_value=True):
            resp = api_client.patch(
                '/api/promotions/P001',
                json={"active": "0"},
                content_type='application/json',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("ok") is True

    def test_update_not_found_returns_404(self, api_client):
        """프로모션이 없으면 404를 반환해야 한다."""
        with patch('src.promotions.engine.PromotionEngine.update_promotion', return_value=False):
            resp = api_client.patch(
                '/api/promotions/NONEXIST',
                json={"active": "0"},
                content_type='application/json',
            )
        assert resp.status_code == 404


class TestPromotionStats:
    def test_stats_returns_200(self, api_client):
        """GET /api/promotions/<id>/stats는 200을 반환해야 한다."""
        with patch('src.promotions.engine.PromotionEngine.get_promo_stats', return_value=SAMPLE_STATS):
            resp = api_client.get('/api/promotions/P001/stats')
        assert resp.status_code == 200

    def test_stats_has_usage_count(self, api_client):
        """stats 응답에 usage_count가 있어야 한다."""
        with patch('src.promotions.engine.PromotionEngine.get_promo_stats', return_value=SAMPLE_STATS):
            resp = api_client.get('/api/promotions/P001/stats')
        data = resp.get_json()
        assert "usage_count" in data

    def test_stats_not_found_returns_404(self, api_client):
        """프로모션이 없으면 404를 반환해야 한다."""
        with patch('src.promotions.engine.PromotionEngine.get_promo_stats', return_value=None):
            resp = api_client.get('/api/promotions/NONEXIST/stats')
        assert resp.status_code == 404
