"""tests/test_crm_api.py — CRM API 엔드포인트 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def api_client(mock_env, monkeypatch):
    """crm_bp가 등록된 Flask 테스트 클라이언트."""
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    with wh.app.test_client() as c:
        yield c


SAMPLE_CUSTOMERS = [
    {
        "email": "vip@example.com",
        "name": "VIP 고객",
        "total_orders": 10,
        "total_spent_krw": 3000000,
        "first_order_date": "2025-01-01T00:00:00+00:00",
        "last_order_date": "2026-03-01T00:00:00+00:00",
        "country": "KR",
        "segment": "VIP",
        "tags": "",
    },
    {
        "email": "new@example.com",
        "name": "신규 고객",
        "total_orders": 1,
        "total_spent_krw": 50000,
        "first_order_date": "2026-03-20T00:00:00+00:00",
        "last_order_date": "2026-03-20T00:00:00+00:00",
        "country": "US",
        "segment": "NEW",
        "tags": "",
    },
]

SAMPLE_SEGMENT_SUMMARY = {
    "VIP": {"count": 1, "avg_spent_krw": 3000000.0, "avg_orders": 10.0},
    "LOYAL": {"count": 0, "avg_spent_krw": 0.0, "avg_orders": 0.0},
    "AT_RISK": {"count": 0, "avg_spent_krw": 0.0, "avg_orders": 0.0},
    "NEW": {"count": 1, "avg_spent_krw": 50000.0, "avg_orders": 1.0},
    "DORMANT": {"count": 0, "avg_spent_krw": 0.0, "avg_orders": 0.0},
}


class TestListCustomers:
    def test_returns_200(self, api_client):
        """GET /api/customers는 200을 반환해야 한다."""
        with patch('src.crm.customer_profile.CustomerProfileManager.get_all_customers',
                   return_value=SAMPLE_CUSTOMERS):
            resp = api_client.get('/api/customers')
        assert resp.status_code == 200

    def test_returns_customer_list(self, api_client):
        """customers 키로 목록이 반환되어야 한다."""
        with patch('src.crm.customer_profile.CustomerProfileManager.get_all_customers',
                   return_value=SAMPLE_CUSTOMERS):
            resp = api_client.get('/api/customers')
        data = resp.get_json()
        assert "customers" in data
        assert data["count"] == 2

    def test_segment_filter(self, api_client):
        """segment 필터가 동작해야 한다."""
        with patch('src.crm.customer_profile.CustomerProfileManager.get_all_customers',
                   return_value=[SAMPLE_CUSTOMERS[0]]) as mock_get:
            resp = api_client.get('/api/customers?segment=VIP')
        assert resp.status_code == 200
        mock_get.assert_called_with(segment='VIP', country=None)

    def test_country_filter(self, api_client):
        """country 필터가 동작해야 한다."""
        with patch('src.crm.customer_profile.CustomerProfileManager.get_all_customers',
                   return_value=[SAMPLE_CUSTOMERS[1]]) as mock_get:
            resp = api_client.get('/api/customers?country=US')
        assert resp.status_code == 200
        mock_get.assert_called_with(segment=None, country='US')


class TestCustomerProfile:
    def test_returns_profile(self, api_client):
        """GET /api/customers/<email>/profile은 프로필을 반환해야 한다."""
        with patch('src.crm.customer_profile.CustomerProfileManager.get_profile',
                   return_value=SAMPLE_CUSTOMERS[0]):
            with patch('src.crm.segmentation.CustomerSegmentation.classify', return_value='VIP'):
                resp = api_client.get('/api/customers/vip%40example.com/profile')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("email") == "vip@example.com"

    def test_not_found_returns_404(self, api_client):
        """고객이 없으면 404를 반환해야 한다."""
        with patch('src.crm.customer_profile.CustomerProfileManager.get_profile',
                   return_value=None):
            resp = api_client.get('/api/customers/nobody%40x.com/profile')
        assert resp.status_code == 404

    def test_profile_has_computed_segment(self, api_client):
        """응답에 computed_segment가 포함되어야 한다."""
        with patch('src.crm.customer_profile.CustomerProfileManager.get_profile',
                   return_value=SAMPLE_CUSTOMERS[0]):
            with patch('src.crm.segmentation.CustomerSegmentation.classify', return_value='VIP'):
                resp = api_client.get('/api/customers/vip%40example.com/profile')
        data = resp.get_json()
        assert "computed_segment" in data


class TestSegmentsSummary:
    def test_returns_200(self, api_client):
        """GET /api/customers/segments/summary는 200을 반환해야 한다."""
        with patch('src.crm.customer_profile.CustomerProfileManager.get_all_customers',
                   return_value=SAMPLE_CUSTOMERS):
            with patch('src.crm.segmentation.CustomerSegmentation.get_segment_summary',
                       return_value=SAMPLE_SEGMENT_SUMMARY):
                resp = api_client.get('/api/customers/segments/summary')
        assert resp.status_code == 200

    def test_returns_segments_key(self, api_client):
        """segments 키로 요약이 반환되어야 한다."""
        with patch('src.crm.customer_profile.CustomerProfileManager.get_all_customers',
                   return_value=SAMPLE_CUSTOMERS):
            with patch('src.crm.segmentation.CustomerSegmentation.get_segment_summary',
                       return_value=SAMPLE_SEGMENT_SUMMARY):
                resp = api_client.get('/api/customers/segments/summary')
        data = resp.get_json()
        assert "segments" in data
