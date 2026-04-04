"""tests/test_subscriptions.py — Phase 92: 구독 결제 관리 시스템 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.subscriptions.plan_manager import PlanManager, Plan, PlanLimits
from src.subscriptions.subscription_manager import SubscriptionManager, SubscriptionStatus
from src.subscriptions.billing import BillingService, InvoiceStatus, PaymentStatus
from src.subscriptions.usage_limiter import UsageLimiter


# ===========================================================================
# PlanManager
# ===========================================================================

class TestPlanManager:
    def test_list_plans(self):
        pm = PlanManager()
        plans = pm.list_plans()
        assert len(plans) == 4
        plan_ids = [p.plan_id for p in plans]
        assert "free" in plan_ids
        assert "starter" in plan_ids
        assert "pro" in plan_ids
        assert "enterprise" in plan_ids

    def test_get_plan_free(self):
        pm = PlanManager()
        plan = pm.get_plan("free")
        assert plan is not None
        assert plan.monthly_price == 0

    def test_get_plan_starter(self):
        pm = PlanManager()
        plan = pm.get_plan("starter")
        assert plan.monthly_price == 29_000

    def test_get_plan_pro(self):
        pm = PlanManager()
        plan = pm.get_plan("pro")
        assert plan.monthly_price == 99_000

    def test_get_plan_enterprise(self):
        pm = PlanManager()
        plan = pm.get_plan("enterprise")
        assert plan.monthly_price == 299_000
        assert plan.limits.max_products == -1  # 무제한

    def test_get_plan_nonexistent(self):
        pm = PlanManager()
        assert pm.get_plan("unknown") is None

    def test_is_valid_plan(self):
        pm = PlanManager()
        assert pm.is_valid_plan("pro") is True
        assert pm.is_valid_plan("invalid") is False

    def test_annual_price_discount(self):
        pm = PlanManager()
        plan = pm.get_plan("starter")
        # 29000 * 0.8 = 23200
        assert plan.annual_price == 23_200

    def test_annual_total(self):
        pm = PlanManager()
        plan = pm.get_plan("starter")
        assert plan.annual_total == 23_200 * 12

    def test_plan_to_dict_monthly(self):
        pm = PlanManager()
        plan = pm.get_plan("pro")
        d = plan.to_dict(billing_cycle="monthly")
        assert d["plan_id"] == "pro"
        assert d["current_price"] == 99_000
        assert "limits" in d
        assert "features" in d

    def test_plan_to_dict_annual(self):
        pm = PlanManager()
        plan = pm.get_plan("pro")
        d = plan.to_dict(billing_cycle="annual")
        assert d["current_price"] == plan.annual_price

    def test_get_comparison_table(self):
        pm = PlanManager()
        table = pm.get_comparison_table()
        assert len(table) == 4

    def test_get_upgrade_path_from_free(self):
        pm = PlanManager()
        paths = pm.get_upgrade_path("free")
        path_ids = [p.plan_id for p in paths]
        assert "starter" in path_ids
        assert "pro" in path_ids
        assert "enterprise" in path_ids
        assert "free" not in path_ids

    def test_get_upgrade_path_from_enterprise(self):
        pm = PlanManager()
        paths = pm.get_upgrade_path("enterprise")
        assert paths == []

    def test_plan_limits_unlimited(self):
        pm = PlanManager()
        plan = pm.get_plan("enterprise")
        assert plan.limits.max_orders_per_month == -1

    def test_plan_limits_to_dict(self):
        pm = PlanManager()
        plan = pm.get_plan("free")
        d = plan.limits.to_dict()
        assert "max_products" in d
        assert "max_orders_per_month" in d


# ===========================================================================
# SubscriptionManager
# ===========================================================================

class TestSubscriptionManagerCreate:
    def test_create_trial(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter", start_trial=True)
        assert sub.subscription_id
        assert sub.status == SubscriptionStatus.TRIAL
        assert sub.trial_ends_at is not None

    def test_create_active_no_trial(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter", start_trial=False)
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.trial_ends_at is None

    def test_create_free_plan_no_trial(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "free", start_trial=True)
        # free 플랜은 trial 없이 active
        assert sub.status == SubscriptionStatus.ACTIVE

    def test_create_annual_billing(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "pro", billing_cycle="annual", start_trial=False)
        assert sub.billing_cycle == "annual"

    def test_create_invalid_billing_cycle(self):
        mgr = SubscriptionManager()
        with pytest.raises(ValueError):
            mgr.create("T1", "U1", "pro", billing_cycle="weekly")

    def test_get_subscription(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter")
        found = mgr.get(sub.subscription_id)
        assert found is not None
        assert found.subscription_id == sub.subscription_id

    def test_get_nonexistent(self):
        mgr = SubscriptionManager()
        assert mgr.get("nonexistent") is None

    def test_list_all(self):
        mgr = SubscriptionManager()
        mgr.create("T1", "U1", "starter")
        mgr.create("T2", "U2", "pro")
        assert len(mgr.list()) == 2

    def test_list_by_tenant(self):
        mgr = SubscriptionManager()
        mgr.create("T1", "U1", "starter")
        mgr.create("T2", "U2", "pro")
        subs = mgr.list(tenant_id="T1")
        assert len(subs) == 1

    def test_list_by_status(self):
        mgr = SubscriptionManager()
        mgr.create("T1", "U1", "starter", start_trial=True)
        mgr.create("T2", "U2", "free")
        trials = mgr.list(status="trial")
        assert len(trials) == 1
        actives = mgr.list(status="active")
        assert len(actives) == 1


class TestSubscriptionManagerTransitions:
    def test_change_plan_upgrade(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter", start_trial=False)
        updated = mgr.change_plan(sub.subscription_id, "pro")
        assert updated.plan_id == "pro"

    def test_change_plan_nonexistent(self):
        mgr = SubscriptionManager()
        with pytest.raises(ValueError):
            mgr.change_plan("nonexistent", "pro")

    def test_change_plan_cancelled_raises(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter", start_trial=False)
        mgr.cancel(sub.subscription_id)
        with pytest.raises(ValueError):
            mgr.change_plan(sub.subscription_id, "pro")

    def test_cancel(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter", start_trial=False)
        cancelled = mgr.cancel(sub.subscription_id, reason="비용 절감")
        assert cancelled.status == SubscriptionStatus.CANCELLED
        assert cancelled.cancelled_at is not None
        assert cancelled.auto_renew is False

    def test_cancel_already_cancelled(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter", start_trial=False)
        mgr.cancel(sub.subscription_id)
        with pytest.raises(ValueError):
            mgr.cancel(sub.subscription_id)

    def test_renew(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter", start_trial=False)
        old_end = sub.current_period_end
        renewed = mgr.renew(sub.subscription_id)
        assert renewed.current_period_end > old_end
        assert renewed.status == SubscriptionStatus.ACTIVE

    def test_renew_cancelled_sub(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter", start_trial=False)
        mgr.cancel(sub.subscription_id)
        sub.auto_renew = False
        with pytest.raises(ValueError):
            mgr.renew(sub.subscription_id)

    def test_transition_trial_to_active(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter", start_trial=True)
        updated = mgr.transition(sub.subscription_id, "active")
        assert updated.status == SubscriptionStatus.ACTIVE

    def test_transition_invalid(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "starter", start_trial=False)
        with pytest.raises(ValueError):
            mgr.transition(sub.subscription_id, "expired")

    def test_to_dict(self):
        mgr = SubscriptionManager()
        sub = mgr.create("T1", "U1", "pro")
        d = sub.to_dict()
        assert "subscription_id" in d
        assert "status" in d
        assert "plan_id" in d


# ===========================================================================
# BillingService
# ===========================================================================

class TestBillingService:
    def test_create_invoice(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        inv = billing.create_invoice("SUB-001", "U1", "starter", "monthly")
        assert inv.invoice_id
        assert inv.amount == 29_000
        assert inv.status == InvoiceStatus.PENDING

    def test_create_invoice_annual(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        inv = billing.create_invoice("SUB-001", "U1", "starter", "annual")
        assert inv.amount == 23_200  # 20% 할인

    def test_create_invoice_invalid_plan(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        with pytest.raises(ValueError):
            billing.create_invoice("SUB-001", "U1", "unknown", "monthly")

    def test_process_payment_success(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        inv = billing.create_invoice("SUB-001", "U1", "free", "monthly")
        result = billing.process_payment(inv.invoice_id)
        assert result["status"] == PaymentStatus.SUCCESS.value
        assert result["receipt"] is not None
        assert inv.status == InvoiceStatus.PAID

    def test_process_payment_failure_retry(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        inv = billing.create_invoice("SUB-001", "U1", "starter", "monthly")
        result = billing.process_payment(inv.invoice_id, force_fail=True)
        assert result["status"] == PaymentStatus.RETRYING.value
        assert inv.retry_count == 1
        assert inv.next_retry_at is not None

    def test_process_payment_max_retry(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        inv = billing.create_invoice("SUB-001", "U1", "starter", "monthly")
        for _ in range(3):
            result = billing.process_payment(inv.invoice_id, force_fail=True)
        assert result["status"] == PaymentStatus.FAILED.value
        assert inv.status == InvoiceStatus.FAILED

    def test_process_payment_already_paid(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        inv = billing.create_invoice("SUB-001", "U1", "free", "monthly")
        billing.process_payment(inv.invoice_id)
        with pytest.raises(ValueError):
            billing.process_payment(inv.invoice_id)

    def test_get_invoice(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        inv = billing.create_invoice("SUB-001", "U1", "pro", "monthly")
        found = billing.get_invoice(inv.invoice_id)
        assert found is not None
        assert found.invoice_id == inv.invoice_id

    def test_get_invoice_nonexistent(self):
        billing = BillingService()
        assert billing.get_invoice("nonexistent") is None

    def test_list_invoices(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        billing.create_invoice("SUB-001", "U1", "starter", "monthly")
        billing.create_invoice("SUB-001", "U1", "starter", "monthly")
        billing.create_invoice("SUB-002", "U2", "pro", "monthly")
        invoices = billing.list_invoices("SUB-001")
        assert len(invoices) == 2

    def test_receipt_issued_on_success(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        inv = billing.create_invoice("SUB-001", "U1", "free", "monthly")
        result = billing.process_payment(inv.invoice_id)
        receipt_id = result["receipt"]["receipt_id"]
        receipt = billing.get_receipt(receipt_id)
        assert receipt is not None
        assert receipt.invoice_id == inv.invoice_id

    def test_invoice_to_dict(self):
        pm = PlanManager()
        billing = BillingService(plan_manager=pm)
        inv = billing.create_invoice("SUB-001", "U1", "starter", "monthly")
        d = inv.to_dict()
        assert "invoice_id" in d
        assert "status" in d
        assert "amount" in d


# ===========================================================================
# UsageLimiter
# ===========================================================================

class TestUsageLimiter:
    def test_get_usage_default(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        usage = limiter.get_usage("T1")
        assert usage.products_count == 0
        assert usage.orders_this_month == 0

    def test_update_usage(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        limiter.update_usage("T1", products_count=100)
        assert limiter.get_usage("T1").products_count == 100

    def test_increment_usage(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        limiter.increment("T1", "api_calls_today", 100)
        limiter.increment("T1", "api_calls_today", 50)
        assert limiter.get_usage("T1").api_calls_today == 150

    def test_check_limit_within(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        limiter.update_usage("T1", products_count=10)
        result = limiter.check_limit("T1", "free", "products")
        assert result["allowed"] is True
        assert result["warning"] is False

    def test_check_limit_warning(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        # free 플랜: max_products=50, 80%=40
        limiter.update_usage("T1", products_count=45)
        result = limiter.check_limit("T1", "free", "products")
        assert result["allowed"] is True
        assert result["warning"] is True

    def test_check_limit_exceeded(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        limiter.update_usage("T1", products_count=60)
        result = limiter.check_limit("T1", "free", "products")
        assert result["allowed"] is False

    def test_check_limit_unlimited(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        limiter.update_usage("T1", products_count=999999)
        result = limiter.check_limit("T1", "enterprise", "products")
        assert result["allowed"] is True
        assert result["limit"] == -1

    def test_check_limit_invalid_resource(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        with pytest.raises(ValueError):
            limiter.check_limit("T1", "free", "invalid_resource")

    def test_check_limit_invalid_plan(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        with pytest.raises(ValueError):
            limiter.check_limit("T1", "unknown_plan", "products")

    def test_get_dashboard(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        dashboard = limiter.get_dashboard("T1", "starter")
        assert "tenant_id" in dashboard
        assert "plan_id" in dashboard
        assert "limits" in dashboard
        assert "products" in dashboard["limits"]
        assert "orders" in dashboard["limits"]

    def test_usage_to_dict(self):
        pm = PlanManager()
        limiter = UsageLimiter(plan_manager=pm)
        rec = limiter.get_usage("T1")
        d = rec.to_dict()
        assert "tenant_id" in d
        assert "products_count" in d


# ===========================================================================
# Subscriptions API (Flask 통합 테스트)
# ===========================================================================

@pytest.fixture
def subs_app():
    """구독 API Blueprint이 등록된 Flask 테스트 클라이언트."""
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    with wh.app.test_client() as c:
        yield c


class TestSubscriptionsAPI:
    def test_list_plans(self, subs_app):
        resp = subs_app.get("/api/v1/subscriptions/plans")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "plans" in data
        assert len(data["plans"]) == 4

    def test_list_plans_annual(self, subs_app):
        resp = subs_app.get("/api/v1/subscriptions/plans?billing_cycle=annual")
        assert resp.status_code == 200

    def test_create_subscription(self, subs_app):
        resp = subs_app.post(
            "/api/v1/subscriptions/",
            json={"tenant_id": "T1", "user_id": "U1", "plan_id": "starter"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "subscription" in data
        assert data["subscription"]["plan_id"] == "starter"

    def test_create_subscription_missing_fields(self, subs_app):
        resp = subs_app.post(
            "/api/v1/subscriptions/",
            json={"tenant_id": "T1"},
        )
        assert resp.status_code == 400

    def test_create_subscription_invalid_plan(self, subs_app):
        resp = subs_app.post(
            "/api/v1/subscriptions/",
            json={"tenant_id": "T1", "user_id": "U1", "plan_id": "invalid_plan"},
        )
        assert resp.status_code == 400

    def test_get_subscription(self, subs_app):
        create_resp = subs_app.post(
            "/api/v1/subscriptions/",
            json={"tenant_id": "T2", "user_id": "U2", "plan_id": "pro"},
        )
        sub_id = create_resp.get_json()["subscription"]["subscription_id"]
        resp = subs_app.get(f"/api/v1/subscriptions/{sub_id}")
        assert resp.status_code == 200

    def test_get_subscription_not_found(self, subs_app):
        resp = subs_app.get("/api/v1/subscriptions/nonexistent")
        assert resp.status_code == 404

    def test_change_plan(self, subs_app):
        create_resp = subs_app.post(
            "/api/v1/subscriptions/",
            json={"tenant_id": "T3", "user_id": "U3", "plan_id": "starter", "start_trial": False},
        )
        sub_id = create_resp.get_json()["subscription"]["subscription_id"]
        resp = subs_app.put(
            f"/api/v1/subscriptions/{sub_id}/plan",
            json={"plan_id": "pro"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["plan_id"] == "pro"

    def test_cancel_subscription(self, subs_app):
        create_resp = subs_app.post(
            "/api/v1/subscriptions/",
            json={"tenant_id": "T4", "user_id": "U4", "plan_id": "starter", "start_trial": False},
        )
        sub_id = create_resp.get_json()["subscription"]["subscription_id"]
        resp = subs_app.post(
            f"/api/v1/subscriptions/{sub_id}/cancel",
            json={"reason": "테스트"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "cancelled"

    def test_list_invoices(self, subs_app):
        create_resp = subs_app.post(
            "/api/v1/subscriptions/",
            json={"tenant_id": "T5", "user_id": "U5", "plan_id": "starter"},
        )
        sub_id = create_resp.get_json()["subscription"]["subscription_id"]
        resp = subs_app.get(f"/api/v1/subscriptions/{sub_id}/invoices")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "invoices" in data

    def test_get_usage(self, subs_app):
        create_resp = subs_app.post(
            "/api/v1/subscriptions/",
            json={"tenant_id": "T6", "user_id": "U6", "plan_id": "pro"},
        )
        sub_id = create_resp.get_json()["subscription"]["subscription_id"]
        resp = subs_app.get(f"/api/v1/subscriptions/{sub_id}/usage")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "limits" in data
