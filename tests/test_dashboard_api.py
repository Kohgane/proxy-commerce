"""tests/test_dashboard_api.py — 대시보드 API 엔드포인트 테스트."""

from unittest.mock import patch

import pytest


@pytest.fixture
def api_client(mock_env, monkeypatch):
    """Dashboard API Blueprint이 등록된 Flask 테스트 클라이언트."""
    monkeypatch.setenv("DASHBOARD_API_ENABLED", "1")
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)

    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    try:
        from src.api import dashboard_bp
        wh.app.register_blueprint(dashboard_bp)
    except Exception:
        pass
    with wh.app.test_client() as c:
        yield c


@pytest.fixture
def sample_orders():
    return [
        {
            "order_id": "10001", "order_number": "#1001",
            "customer_name": "홍길동", "customer_email": "hong@example.com",
            "order_date": "2026-03-01T10:00:00Z", "sku": "PTR-TNK-001",
            "vendor": "PORTER", "buy_price": 30800, "buy_currency": "JPY",
            "sell_price_krw": 370000, "sell_price_usd": 266.0, "margin_pct": 18.0,
            "status": "paid", "status_updated_at": "2026-03-01T10:01:00Z",
            "shipping_country": "KR",
        }
    ]


@pytest.fixture
def sample_catalog():
    return [
        {
            "sku": "PTR-TNK-001", "title_ko": "포터 탱커", "title_en": "Porter Tanker",
            "vendor": "porter", "buy_currency": "JPY", "buy_price": 30800,
            "sell_price_krw": 370000, "margin_pct": 18.0, "stock": 5,
            "stock_status": "in_stock", "status": "active", "source_country": "JP",
        },
        {
            "sku": "MMP-EDP-001", "title_ko": "메모파리", "title_en": "Memo Paris",
            "vendor": "memo_paris", "buy_currency": "EUR", "buy_price": 250.0,
            "sell_price_krw": 420000, "margin_pct": 20.0, "stock": 1,
            "stock_status": "low_stock", "status": "active", "source_country": "FR",
        },
    ]


class TestDashboardSummary:
    def test_summary_returns_200(self, api_client, sample_orders, sample_catalog):
        with patch("src.api.dashboard_routes._load_orders", return_value=sample_orders), \
             patch("src.api.dashboard_routes._load_catalog", return_value=sample_catalog), \
             patch("src.api.dashboard_routes._get_fx_rates", return_value={}), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "orders" in data
        assert "revenue" in data
        assert "inventory" in data
        assert "timestamp" in data

    def test_summary_order_counts(self, api_client, sample_orders, sample_catalog):
        with patch("src.api.dashboard_routes._load_orders", return_value=sample_orders), \
             patch("src.api.dashboard_routes._load_catalog", return_value=sample_catalog), \
             patch("src.api.dashboard_routes._get_fx_rates", return_value={}), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/summary")
        data = resp.get_json()
        assert data["orders"]["total"] == 1
        assert data["orders"]["pending"] == 1


class TestDashboardOrders:
    def test_orders_list_returns_200(self, api_client, sample_orders):
        with patch("src.api.dashboard_routes._load_orders", return_value=sample_orders), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/orders")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "items" in data
        assert "pagination" in data

    def test_orders_status_filter(self, api_client, sample_orders):
        with patch("src.api.dashboard_routes._load_orders", return_value=sample_orders), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/orders?status=shipped")
        data = resp.get_json()
        assert data["items"] == []

    def test_orders_pagination(self, api_client, sample_orders):
        with patch("src.api.dashboard_routes._load_orders", return_value=sample_orders * 5), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/orders?page=1&per_page=2")
        data = resp.get_json()
        assert len(data["items"]) == 2
        assert data["pagination"]["per_page"] == 2

    def test_order_detail_found(self, api_client, sample_orders):
        with patch("src.api.dashboard_routes._load_orders", return_value=sample_orders), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/orders/10001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["order_id"] == "10001"

    def test_order_detail_not_found(self, api_client, sample_orders):
        with patch("src.api.dashboard_routes._load_orders", return_value=sample_orders), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/orders/99999")
        assert resp.status_code == 404


class TestDashboardRevenue:
    def test_revenue_daily(self, api_client, sample_orders):
        with patch("src.api.dashboard_routes._load_orders", return_value=sample_orders), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/revenue?period=daily")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["period"] == "daily"
        assert "total_revenue_krw" in data

    def test_revenue_invalid_period_defaults_daily(self, api_client, sample_orders):
        with patch("src.api.dashboard_routes._load_orders", return_value=sample_orders), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/revenue?period=invalid")
        data = resp.get_json()
        assert data["period"] == "daily"


class TestDashboardInventory:
    def test_inventory_returns_200(self, api_client, sample_catalog):
        with patch("src.api.dashboard_routes._load_catalog", return_value=sample_catalog), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/inventory")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "items" in data
        assert "low_stock_threshold" in data

    def test_inventory_low_stock_filter(self, api_client, sample_catalog):
        with patch("src.api.dashboard_routes._load_catalog", return_value=sample_catalog), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/inventory?low_stock=true")
        data = resp.get_json()
        # stock=1 항목이 low_stock 기준(3) 이하 → 1개
        assert len(data["items"]) == 1


class TestDashboardFx:
    def test_fx_returns_200(self, api_client):
        fx_data = {"USDKRW": 1380.0, "JPYKRW": 9.2}
        with patch("src.api.dashboard_routes._get_fx_rates", return_value=fx_data), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/fx")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "rates" in data
        assert "timestamp" in data


class TestDashboardHealth:
    def test_health_returns_json(self, api_client):
        with patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/health")
        assert resp.status_code in (200, 503)
        data = resp.get_json()
        assert "status" in data
        assert "checks" in data


class TestDashboardDisabled:
    def test_disabled_returns_503(self, api_client, monkeypatch):
        monkeypatch.setenv("DASHBOARD_API_ENABLED", "0")
        with patch("src.api.dashboard_routes._API_ENABLED", False), \
             patch("src.api.auth_middleware._audit") as mock_audit:
            mock_audit.log.return_value = {}
            resp = api_client.get("/api/dashboard/summary")
        assert resp.status_code == 503
