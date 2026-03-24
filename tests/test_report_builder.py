"""tests/test_report_builder.py — ReportBuilder 테스트."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def builder(mock_env):
    """ReportBuilder 인스턴스."""
    from src.reporting.report_builder import ReportBuilder
    return ReportBuilder(sheet_id="fake_id")


def _mock_ws(records=None):
    ws = MagicMock()
    ws.get_all_records.return_value = records or []
    return ws


SAMPLE_ORDERS = [
    {"created_at": "2026-01-15", "total_price_krw": 50000, "channel": "shopify"},
    {"created_at": "2026-01-16", "total_price_krw": 80000, "channel": "woocommerce"},
]
SAMPLE_PRODUCTS = [
    {"sku": "SKU001", "stock_qty": 0},
    {"sku": "SKU002", "stock_qty": 3},
    {"sku": "SKU003", "stock_qty": 50},
]
SAMPLE_CUSTOMERS = [
    {"email": "a@b.com", "first_order_date": "2026-01-01", "segment": "VIP"},
    {"email": "c@d.com", "first_order_date": "2026-01-10", "segment": "NEW"},
]
SAMPLE_CAMPAIGNS = [
    {"campaign_id": "c1", "status": "active", "budget_krw": 100000, "spent_krw": 30000},
    {"campaign_id": "c2", "status": "completed", "budget_krw": 50000, "spent_krw": 50000},
]


class TestSalesReport:
    def test_sales_report_keys(self, builder):
        """매출 리포트는 필수 키를 포함해야 한다."""
        ws = _mock_ws(SAMPLE_ORDERS)
        with patch('src.reporting.report_builder.open_sheet', return_value=ws):
            report = builder.generate_report("sales")
        assert report["report_type"] == "sales"
        assert "total_orders" in report
        assert "total_revenue_krw" in report
        assert "avg_order_krw" in report
        assert "by_channel" in report
        assert "generated_at" in report

    def test_sales_report_values(self, builder):
        """매출 리포트 값이 올바르게 계산되어야 한다."""
        ws = _mock_ws(SAMPLE_ORDERS)
        with patch('src.reporting.report_builder.open_sheet', return_value=ws):
            report = builder.generate_report("sales")
        assert report["total_orders"] == 2
        assert report["total_revenue_krw"] == 130000.0


class TestInventoryReport:
    def test_inventory_report_keys(self, builder):
        """재고 리포트는 필수 키를 포함해야 한다."""
        ws = _mock_ws(SAMPLE_PRODUCTS)
        with patch('src.reporting.report_builder.open_sheet', return_value=ws):
            report = builder.generate_report("inventory")
        assert report["report_type"] == "inventory"
        assert "total_skus" in report
        assert "in_stock" in report
        assert "out_of_stock" in report
        assert "low_stock" in report
        assert "dead_stock" in report
        assert "generated_at" in report

    def test_inventory_report_values(self, builder):
        """재고 리포트 값이 올바르게 계산되어야 한다."""
        ws = _mock_ws(SAMPLE_PRODUCTS)
        with patch('src.reporting.report_builder.open_sheet', return_value=ws):
            report = builder.generate_report("inventory")
        assert report["total_skus"] == 3
        assert report["out_of_stock"] == 1
        assert report["low_stock"] == 1


class TestCustomerReport:
    def test_customer_report_keys(self, builder):
        """고객 리포트는 필수 키를 포함해야 한다."""
        ws = _mock_ws(SAMPLE_CUSTOMERS)
        with patch('src.reporting.report_builder.open_sheet', return_value=ws):
            report = builder.generate_report("customers")
        assert report["report_type"] == "customers"
        assert "total_customers" in report
        assert "by_segment" in report
        assert "new_customers" in report
        assert "generated_at" in report


class TestMarketingReport:
    def test_marketing_report_keys(self, builder):
        """마케팅 리포트는 필수 키를 포함해야 한다."""
        ws = _mock_ws(SAMPLE_CAMPAIGNS)
        with patch('src.reporting.report_builder.open_sheet', return_value=ws):
            report = builder.generate_report("marketing")
        assert report["report_type"] == "marketing"
        assert "total_campaigns" in report
        assert "active_campaigns" in report
        assert "total_budget_krw" in report
        assert "total_spent_krw" in report
        assert "roi" in report
        assert "generated_at" in report


class TestInvalidReportType:
    def test_generate_report_invalid_type(self, builder):
        """잘못된 리포트 타입은 오류 딕셔너리를 반환해야 한다."""
        with patch('src.reporting.report_builder.open_sheet', return_value=_mock_ws()):
            report = builder.generate_report("invalid_type")
        assert "error" in report
