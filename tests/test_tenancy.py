"""tests/test_tenancy.py — 멀티테넌시 모듈 테스트 (Phase 49)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────────────────────────────────────────────────
# TenantManager
# ─────────────────────────────────────────────────────────────

class TestTenantManager:
    def setup_method(self):
        from src.tenancy.tenant_manager import TenantManager
        self.mgr = TenantManager()

    def test_create_tenant(self):
        t = self.mgr.create("Acme Corp", "admin@acme.com")
        assert t["name"] == "Acme Corp"
        assert t["owner_email"] == "admin@acme.com"
        assert t["active"] is True
        assert "tenant_id" in t

    def test_create_requires_name(self):
        with pytest.raises(ValueError):
            self.mgr.create("", "admin@example.com")

    def test_create_requires_email(self):
        with pytest.raises(ValueError):
            self.mgr.create("Corp", "")

    def test_get_existing(self):
        t = self.mgr.create("Shop A", "a@shop.com")
        fetched = self.mgr.get(t["tenant_id"])
        assert fetched["name"] == "Shop A"

    def test_get_nonexistent_returns_none(self):
        assert self.mgr.get("no-such-id") is None

    def test_list_returns_all(self):
        self.mgr.create("T1", "t1@x.com")
        self.mgr.create("T2", "t2@x.com")
        assert len(self.mgr.list()) == 2

    def test_list_active_only(self):
        t1 = self.mgr.create("T1", "t1@x.com")
        t2 = self.mgr.create("T2", "t2@x.com")
        self.mgr.deactivate(t2["tenant_id"])
        active = self.mgr.list(active_only=True)
        assert len(active) == 1
        assert active[0]["tenant_id"] == t1["tenant_id"]

    def test_update_tenant(self):
        t = self.mgr.create("Old Name", "old@x.com")
        updated = self.mgr.update(t["tenant_id"], name="New Name")
        assert updated["name"] == "New Name"

    def test_update_nonexistent_raises(self):
        with pytest.raises(KeyError):
            self.mgr.update("no-id", name="X")

    def test_deactivate(self):
        t = self.mgr.create("Corp", "x@x.com")
        result = self.mgr.deactivate(t["tenant_id"])
        assert result["active"] is False

    def test_delete(self):
        t = self.mgr.create("Corp", "x@x.com")
        assert self.mgr.delete(t["tenant_id"]) is True
        assert self.mgr.get(t["tenant_id"]) is None

    def test_delete_nonexistent_returns_false(self):
        assert self.mgr.delete("no-id") is False


# ─────────────────────────────────────────────────────────────
# TenantConfig
# ─────────────────────────────────────────────────────────────

class TestTenantConfig:
    def setup_method(self):
        from src.tenancy.tenant_config import TenantConfig
        self.cfg = TenantConfig()

    def test_get_default(self):
        config = self.cfg.get("new-tenant")
        assert "margin_rate" in config
        assert config["margin_rate"] == 0.20

    def test_set_and_get(self):
        self.cfg.set("t1", margin_rate=0.30, currency="USD")
        config = self.cfg.get("t1")
        assert config["margin_rate"] == 0.30
        assert config["currency"] == "USD"

    def test_get_field(self):
        self.cfg.set("t2", fx_strategy="fixed")
        assert self.cfg.get_field("t2", "fx_strategy") == "fixed"

    def test_reset(self):
        self.cfg.set("t3", margin_rate=0.99)
        reset = self.cfg.reset("t3")
        assert reset["margin_rate"] == 0.20

    def test_delete(self):
        self.cfg.set("t4", margin_rate=0.5)
        assert self.cfg.delete("t4") is True
        assert self.cfg.delete("t4") is False


# ─────────────────────────────────────────────────────────────
# TenantIsolation
# ─────────────────────────────────────────────────────────────

class TestTenantIsolation:
    def setup_method(self):
        from src.tenancy.tenant_isolation import TenantIsolation
        self.iso = TenantIsolation()

    def test_filter(self):
        records = [
            {"id": 1, "tenant_id": "t1"},
            {"id": 2, "tenant_id": "t2"},
            {"id": 3, "tenant_id": "t1"},
        ]
        result = self.iso.filter(records, "t1")
        assert len(result) == 2
        assert all(r["tenant_id"] == "t1" for r in result)

    def test_tag(self):
        record = {"id": 1, "name": "product"}
        tagged = self.iso.tag(record, "tenant-abc")
        assert tagged["tenant_id"] == "tenant-abc"
        assert tagged["name"] == "product"

    def test_tag_many(self):
        records = [{"id": i} for i in range(5)]
        tagged = self.iso.tag_many(records, "t-x")
        assert all(r["tenant_id"] == "t-x" for r in tagged)

    def test_validate_access(self):
        record = {"id": 1, "tenant_id": "t1"}
        assert self.iso.validate_access(record, "t1") is True
        assert self.iso.validate_access(record, "t2") is False

    def test_strip_tag(self):
        record = {"id": 1, "tenant_id": "t1", "name": "x"}
        stripped = self.iso.strip_tag(record)
        assert "tenant_id" not in stripped
        assert "name" in stripped


# ─────────────────────────────────────────────────────────────
# SubscriptionPlan
# ─────────────────────────────────────────────────────────────

class TestSubscriptionPlan:
    def setup_method(self):
        from src.tenancy.subscription_plan import SubscriptionPlan
        self.plans = SubscriptionPlan()

    def test_get_free_plan(self):
        plan = self.plans.get_plan("free")
        assert plan["monthly_api_calls"] == 1_000
        assert plan["price_krw"] == 0

    def test_get_enterprise_plan(self):
        plan = self.plans.get_plan("enterprise")
        assert plan["monthly_api_calls"] == -1  # unlimited

    def test_list_plans(self):
        plans = self.plans.list_plans()
        assert len(plans) == 4
        tiers = [p["tier"] for p in plans]
        assert "free" in tiers
        assert "enterprise" in tiers

    def test_check_limit_within(self):
        # Free plan has monthly_orders limit of 50; usage of 50 is at limit (<=), should be True
        assert self.plans.check_limit("free", "monthly_orders", 50) is True
        assert self.plans.check_limit("free", "monthly_orders", 10) is True

    def test_check_limit_exceeded(self):
        assert self.plans.check_limit("free", "monthly_orders", 51) is False

    def test_check_limit_enterprise_unlimited(self):
        assert self.plans.check_limit("enterprise", "monthly_orders", 999999) is True

    def test_has_feature(self):
        assert self.plans.has_feature("pro", "ab_testing") is True
        assert self.plans.has_feature("free", "ab_testing") is False

    def test_enterprise_has_all(self):
        assert self.plans.has_feature("enterprise", "any_feature") is True

    def test_upgrade_path(self):
        assert self.plans.upgrade_path("free") == "basic"
        assert self.plans.upgrade_path("basic") == "pro"
        assert self.plans.upgrade_path("enterprise") is None


# ─────────────────────────────────────────────────────────────
# UsageTracker
# ─────────────────────────────────────────────────────────────

class TestUsageTracker:
    def setup_method(self):
        from src.tenancy.usage_tracker import UsageTracker
        self.tracker = UsageTracker()

    def test_increment(self):
        val = self.tracker.increment("t1", "api_calls")
        assert val == 1
        val = self.tracker.increment("t1", "api_calls", 5)
        assert val == 6

    def test_get_default(self):
        usage = self.tracker.get("no-tenant")
        assert usage["api_calls"] == 0
        assert usage["orders"] == 0

    def test_get_resource(self):
        self.tracker.increment("t2", "orders", 3)
        assert self.tracker.get_resource("t2", "orders") == 3

    def test_reset_resource(self):
        self.tracker.increment("t3", "api_calls", 100)
        self.tracker.reset("t3", "api_calls")
        assert self.tracker.get_resource("t3", "api_calls") == 0

    def test_reset_all(self):
        self.tracker.increment("t4", "products", 50)
        self.tracker.reset("t4")
        assert self.tracker.get_resource("t4", "products") == 0

    def test_summary(self):
        self.tracker.increment("t5", "api_calls", 10)
        summary = self.tracker.summary()
        tenant_ids = [s["tenant_id"] for s in summary]
        assert "t5" in tenant_ids


# ─────────────────────────────────────────────────────────────
# Tenancy API Blueprint
# ─────────────────────────────────────────────────────────────

class TestTenancyAPI:
    def setup_method(self):
        from flask import Flask
        from src.api.tenancy_api import tenancy_bp
        app = Flask(__name__)
        app.register_blueprint(tenancy_bp)
        self.client = app.test_client()

    def test_status(self):
        resp = self.client.get("/api/v1/tenants/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_list_empty(self):
        resp = self.client.get("/api/v1/tenants/")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_create_and_get(self):
        resp = self.client.post("/api/v1/tenants/", json={
            "name": "Test Corp", "owner_email": "test@corp.com"
        })
        assert resp.status_code == 201
        tenant = resp.get_json()
        tid = tenant["tenant_id"]

        resp2 = self.client.get(f"/api/v1/tenants/{tid}")
        assert resp2.status_code == 200
        assert resp2.get_json()["name"] == "Test Corp"

    def test_create_missing_fields(self):
        resp = self.client.post("/api/v1/tenants/", json={"name": ""})
        assert resp.status_code == 400

    def test_get_nonexistent(self):
        resp = self.client.get("/api/v1/tenants/no-such-id")
        assert resp.status_code == 404

    def test_list_plans(self):
        resp = self.client.get("/api/v1/tenants/plans")
        assert resp.status_code == 200
        plans = resp.get_json()
        assert len(plans) == 4
