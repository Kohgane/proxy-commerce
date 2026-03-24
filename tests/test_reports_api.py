"""tests/test_reports_api.py — 리포트 API 엔드포인트 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def api_client(mock_env, monkeypatch):
    """reports_bp가 등록된 Flask 테스트 클라이언트."""
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    with wh.app.test_client() as c:
        yield c


SAMPLE_SALES_REPORT = {
    "report_type": "sales",
    "period": {"start": None, "end": None},
    "total_orders": 10,
    "total_revenue_krw": 500000.0,
    "avg_order_krw": 50000.0,
    "by_channel": {"shopify": 10},
    "generated_at": "2026-01-01T00:00:00",
}
SAMPLE_INVENTORY_REPORT = {
    "report_type": "inventory",
    "total_skus": 50,
    "in_stock": 40,
    "out_of_stock": 5,
    "low_stock": 3,
    "dead_stock": 2,
    "generated_at": "2026-01-01T00:00:00",
}
SAMPLE_CUSTOMER_REPORT = {
    "report_type": "customers",
    "total_customers": 100,
    "new_customers": 10,
    "by_segment": {"VIP": 5, "NEW": 10},
    "generated_at": "2026-01-01T00:00:00",
}
SAMPLE_MARKETING_REPORT = {
    "report_type": "marketing",
    "total_campaigns": 5,
    "active_campaigns": 2,
    "total_budget_krw": 500000.0,
    "total_spent_krw": 200000.0,
    "roi": 40.0,
    "generated_at": "2026-01-01T00:00:00",
}


class TestGetSalesReport:
    def test_get_sales_report(self, api_client):
        """GET /api/reports/sales는 매출 리포트를 반환해야 한다."""
        with patch('src.reporting.report_builder.ReportBuilder.generate_report',
                   return_value=SAMPLE_SALES_REPORT):
            resp = api_client.get('/api/reports/sales')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["report_type"] == "sales"
        assert "total_orders" in data


class TestGetInventoryReport:
    def test_get_inventory_report(self, api_client):
        """GET /api/reports/inventory는 재고 리포트를 반환해야 한다."""
        with patch('src.reporting.report_builder.ReportBuilder.generate_report',
                   return_value=SAMPLE_INVENTORY_REPORT):
            resp = api_client.get('/api/reports/inventory')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["report_type"] == "inventory"


class TestGetCustomerReport:
    def test_get_customer_report(self, api_client):
        """GET /api/reports/customers는 고객 리포트를 반환해야 한다."""
        with patch('src.reporting.report_builder.ReportBuilder.generate_report',
                   return_value=SAMPLE_CUSTOMER_REPORT):
            resp = api_client.get('/api/reports/customers')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["report_type"] == "customers"


class TestGetMarketingReport:
    def test_get_marketing_report(self, api_client):
        """GET /api/reports/marketing은 마케팅 리포트를 반환해야 한다."""
        with patch('src.reporting.report_builder.ReportBuilder.generate_report',
                   return_value=SAMPLE_MARKETING_REPORT):
            resp = api_client.get('/api/reports/marketing')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["report_type"] == "marketing"


class TestPostGenerateReport:
    def test_post_generate_report_sales(self, api_client):
        """POST /api/reports/generate는 지정된 리포트를 반환해야 한다."""
        with patch('src.reporting.report_builder.ReportBuilder.generate_report',
                   return_value=SAMPLE_SALES_REPORT):
            resp = api_client.post('/api/reports/generate', json={
                "report_type": "sales",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["report_type"] == "sales"

    def test_post_generate_report_invalid_type(self, api_client):
        """POST /api/reports/generate에 잘못된 타입은 400을 반환해야 한다."""
        with patch('src.reporting.report_builder.ReportBuilder.generate_report',
                   return_value={"error": "알 수 없는 리포트 타입", "valid_types": []}):
            resp = api_client.post('/api/reports/generate', json={
                "report_type": "invalid",
            })
        assert resp.status_code == 400
