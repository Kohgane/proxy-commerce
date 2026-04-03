"""tests/test_tenancy.py — Phase 49: 멀티테넌시 테스트."""
import pytest
from src.tenancy.tenant_manager import TenantManager
from src.tenancy.tenant_config import TenantConfig
from src.tenancy.tenant_isolation import TenantIsolation
from src.tenancy.subscription_plan import SubscriptionPlan, PLANS
from src.tenancy.usage_tracker import UsageTracker


class TestTenantManager:
    def setup_method(self):
        self.mgr = TenantManager()

    def test_create_tenant(self):
        t = self.mgr.create('Tenant A')
        assert t['name'] == 'Tenant A'
        assert t['status'] == 'active'
        assert t['plan'] == 'free'
        assert 'id' in t

    def test_create_with_plan(self):
        t = self.mgr.create('Tenant B', plan='pro')
        assert t['plan'] == 'pro'

    def test_get_tenant(self):
        t = self.mgr.create('Tenant C')
        found = self.mgr.get(t['id'])
        assert found is not None
        assert found['name'] == 'Tenant C'

    def test_get_missing(self):
        assert self.mgr.get('no-such-id') is None

    def test_list_tenants(self):
        self.mgr.create('T1')
        self.mgr.create('T2')
        tenants = self.mgr.list_tenants()
        assert len(tenants) == 2

    def test_update_tenant(self):
        t = self.mgr.create('Old Name')
        updated = self.mgr.update(t['id'], name='New Name')
        assert updated['name'] == 'New Name'

    def test_update_missing(self):
        with pytest.raises(KeyError):
            self.mgr.update('bad-id', name='x')

    def test_deactivate(self):
        t = self.mgr.create('Tenant D')
        result = self.mgr.deactivate(t['id'])
        assert result['status'] == 'inactive'

    def test_deactivate_missing(self):
        with pytest.raises(KeyError):
            self.mgr.deactivate('bad-id')

    def test_create_with_config(self):
        t = self.mgr.create('Tenant E', config={'key': 'val'})
        assert t['config']['key'] == 'val'


class TestTenantConfig:
    def setup_method(self):
        self.cfg = TenantConfig()

    def test_default_config(self):
        config = self.cfg.get_config('t1')
        assert config['margin_rate'] == 0.2
        assert config['currency_strategy'] == 'fixed'

    def test_set_config(self):
        self.cfg.set_config('t1', margin_rate=0.3)
        config = self.cfg.get_config('t1')
        assert config['margin_rate'] == 0.3

    def test_update_config(self):
        self.cfg.set_config('t2', shipping_policy='express')
        self.cfg.update_config('t2', margin_rate=0.15)
        config = self.cfg.get_config('t2')
        assert config['shipping_policy'] == 'express'
        assert config['margin_rate'] == 0.15


class TestTenantIsolation:
    def setup_method(self):
        self.iso = TenantIsolation()

    def test_filter_by_tenant(self):
        items = [
            {'tenant_id': 'a', 'val': 1},
            {'tenant_id': 'b', 'val': 2},
            {'tenant_id': 'a', 'val': 3},
        ]
        result = self.iso.filter_by_tenant(items, 'a')
        assert len(result) == 2

    def test_filter_empty(self):
        assert self.iso.filter_by_tenant([], 'a') == []

    def test_add_tenant_id(self):
        item = {'val': 1}
        result = self.iso.add_tenant_id(item, 'abc')
        assert result['tenant_id'] == 'abc'


class TestSubscriptionPlan:
    def setup_method(self):
        self.sp = SubscriptionPlan()

    def test_get_plan(self):
        plan = self.sp.get_plan('free')
        assert plan is not None
        assert plan['name'] == 'Free'

    def test_get_missing_plan(self):
        assert self.sp.get_plan('nonexistent') is None

    def test_all_plans_exist(self):
        for name in ('free', 'basic', 'pro', 'enterprise'):
            assert self.sp.get_plan(name) is not None

    def test_check_limit_within(self):
        assert self.sp.check_limit('free', 'max_products', 50) is True

    def test_check_limit_exceeded(self):
        assert self.sp.check_limit('free', 'max_products', 150) is False

    def test_check_limit_enterprise_unlimited(self):
        assert self.sp.check_limit('enterprise', 'max_products', 999999) is True

    def test_check_limit_unknown_plan(self):
        assert self.sp.check_limit('unknown', 'max_products', 10) is False


class TestUsageTracker:
    def setup_method(self):
        self.tracker = UsageTracker()

    def test_track(self):
        val = self.tracker.track('t1', 'api_calls')
        assert val == 1

    def test_track_increment(self):
        self.tracker.track('t1', 'api_calls', 5)
        val = self.tracker.track('t1', 'api_calls', 3)
        assert val == 8

    def test_get_usage(self):
        self.tracker.track('t2', 'orders', 10)
        usage = self.tracker.get_usage('t2')
        assert usage['orders'] == 10

    def test_get_usage_empty(self):
        assert self.tracker.get_usage('unknown') == {}

    def test_reset_usage(self):
        self.tracker.track('t3', 'products', 5)
        self.tracker.reset_usage('t3')
        assert self.tracker.get_usage('t3') == {}
