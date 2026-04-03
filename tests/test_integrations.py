"""tests/test_integrations.py — Phase 60: 외부 연동 허브 테스트."""
from __future__ import annotations

import pytest
from src.integrations.integration_connector import IntegrationConnector
from src.integrations.integration_registry import IntegrationRegistry
from src.integrations.slack_connector import SlackConnector
from src.integrations.google_sheets_connector import GoogleSheetsConnector
from src.integrations.shopify_connector import ShopifyConnector
from src.integrations.connection_health_check import ConnectionHealthCheck
from src.integrations.sync_scheduler import SyncScheduler
from src.integrations.integration_log import IntegrationLog


class TestIntegrationRegistry:
    def setup_method(self):
        self.registry = IntegrationRegistry()

    def test_register_and_list(self):
        connector = SlackConnector()
        self.registry.register(connector)
        assert "slack" in self.registry.list_all()

    def test_get_connector(self):
        connector = SlackConnector()
        self.registry.register(connector)
        result = self.registry.get("slack")
        assert result is connector

    def test_get_missing(self):
        assert self.registry.get("nonexistent") is None

    def test_unregister(self):
        self.registry.register(SlackConnector())
        self.registry.unregister("slack")
        assert "slack" not in self.registry.list_all()

    def test_list_active(self):
        self.registry.register(SlackConnector())
        assert "slack" not in self.registry.list_active()
        self.registry.set_active("slack", True)
        assert "slack" in self.registry.list_active()


class TestSlackConnector:
    def setup_method(self):
        self.connector = SlackConnector()

    def test_is_integration_connector(self):
        assert isinstance(self.connector, IntegrationConnector)

    def test_connect(self):
        assert self.connector.connect() is True

    def test_disconnect(self):
        self.connector.connect()
        assert self.connector.disconnect() is True

    def test_health_check_disconnected(self):
        result = self.connector.health_check()
        assert result["status"] == "disconnected"

    def test_health_check_connected(self):
        self.connector.connect()
        result = self.connector.health_check()
        assert result["status"] == "ok"

    def test_send_message(self):
        result = self.connector.send_message("#general", "Hello")
        assert result["ok"] is True
        messages = self.connector.get_messages()
        assert len(messages) == 1

    def test_sync(self):
        result = self.connector.sync()
        assert result["synced"] is True


class TestGoogleSheetsConnector:
    def setup_method(self):
        self.connector = GoogleSheetsConnector()

    def test_connect(self):
        assert self.connector.connect() is True

    def test_read_sheet_default(self):
        data = self.connector.read_sheet("sheet1")
        assert isinstance(data, list)
        assert len(data) > 0

    def test_write_and_read_sheet(self):
        test_data = [["id", "name"], ["1", "product1"]]
        result = self.connector.write_sheet("sheet1", test_data)
        assert result["rows_written"] == 2
        read_back = self.connector.read_sheet("sheet1")
        assert read_back == test_data

    def test_sync(self):
        result = self.connector.sync()
        assert result["synced"] is True

    def test_health_check(self):
        self.connector.connect()
        result = self.connector.health_check()
        assert result["status"] == "ok"


class TestShopifyConnector:
    def setup_method(self):
        self.connector = ShopifyConnector()

    def test_connect(self):
        assert self.connector.connect() is True

    def test_get_orders(self):
        orders = self.connector.get_orders()
        assert isinstance(orders, list)
        assert len(orders) > 0

    def test_get_products(self):
        products = self.connector.get_products()
        assert isinstance(products, list)
        assert len(products) > 0

    def test_sync(self):
        result = self.connector.sync()
        assert result["synced"] is True
        assert "orders" in result
        assert "products" in result

    def test_health_check(self):
        self.connector.connect()
        result = self.connector.health_check()
        assert result["status"] == "ok"


class TestConnectionHealthCheck:
    def setup_method(self):
        self.registry = IntegrationRegistry()
        self.health_check = ConnectionHealthCheck()

    def test_check_all(self):
        self.registry.register(SlackConnector())
        self.registry.register(ShopifyConnector())
        results = self.health_check.check_all(self.registry)
        assert "slack" in results
        assert "shopify" in results

    def test_check_one(self):
        connector = SlackConnector()
        connector.connect()
        self.registry.register(connector)
        result = self.health_check.check_one("slack", self.registry)
        assert result["status"] == "ok"

    def test_check_one_missing(self):
        result = self.health_check.check_one("nonexistent", self.registry)
        assert result["status"] == "not_found"


class TestSyncScheduler:
    def setup_method(self):
        self.scheduler = SyncScheduler()
        self.registry = IntegrationRegistry()
        connector = SlackConnector()
        connector.connect()
        self.registry.register(connector)

    def test_schedule(self):
        self.scheduler.schedule("slack", interval_seconds=60)
        schedule = self.scheduler.get_schedule()
        assert len(schedule) == 1
        assert schedule[0]["name"] == "slack"

    def test_run_due_syncs(self):
        # interval=0 ensures immediate execution
        self.scheduler.schedule("slack", interval_seconds=0)
        results = self.scheduler.run_due_syncs(self.registry)
        assert len(results) == 1
        assert results[0]["name"] == "slack"
        assert results[0]["status"] == "ok"

    def test_run_not_due(self):
        self.scheduler.schedule("slack", interval_seconds=99999)
        results = self.scheduler.run_due_syncs(self.registry)
        assert results == []


class TestIntegrationLog:
    def setup_method(self):
        self.log = IntegrationLog()

    def test_record_and_get(self):
        self.log.record("slack", True, "connected")
        entries = self.log.get_log()
        assert len(entries) == 1

    def test_filter_by_name(self):
        self.log.record("slack", True, "ok")
        self.log.record("shopify", True, "ok")
        entries = self.log.get_log(name="slack")
        assert len(entries) == 1
        assert entries[0]["name"] == "slack"

    def test_get_stats(self):
        self.log.record("slack", True, "ok")
        self.log.record("slack", True, "ok")
        self.log.record("slack", False, "error", error="timeout")
        stats = self.log.get_stats("slack")
        assert stats["total"] == 3
        assert stats["successes"] == 2
        assert stats["failures"] == 1
        assert stats["success_rate"] == pytest.approx(66.67, rel=0.01)
