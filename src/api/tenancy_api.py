"""src/api/tenancy_api.py — 멀티테넌시 API Blueprint (Phase 49)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

tenancy_bp = Blueprint("tenancy", __name__, url_prefix="/api/v1/tenants")

_manager = None
_config = None
_usage = None
_plans = None


def _get_services():
    global _manager, _config, _usage, _plans
    if _manager is None:
        from ..tenancy.tenant_manager import TenantManager
        from ..tenancy.tenant_config import TenantConfig
        from ..tenancy.usage_tracker import UsageTracker
        from ..tenancy.subscription_plan import SubscriptionPlan
        _manager = TenantManager()
        _config = TenantConfig()
        _usage = UsageTracker()
        _plans = SubscriptionPlan()
    return _manager, _config, _usage, _plans


@tenancy_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "tenancy"})


@tenancy_bp.get("/")
def list_tenants():
    mgr, _, _, _ = _get_services()
    active_only = request.args.get("active_only", "false").lower() == "true"
    return jsonify(mgr.list(active_only=active_only))


@tenancy_bp.post("/")
def create_tenant():
    mgr, _, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    try:
        tenant = mgr.create(
            name=data.get("name", ""),
            owner_email=data.get("owner_email", ""),
            plan=data.get("plan", "free"),
        )
        return jsonify(tenant), 201
    except ValueError:
        return jsonify({"error": "name과 owner_email은 필수입니다."}), 400


@tenancy_bp.get("/<tenant_id>")
def get_tenant(tenant_id: str):
    mgr, _, _, _ = _get_services()
    tenant = mgr.get(tenant_id)
    if not tenant:
        return jsonify({"error": "테넌트 없음"}), 404
    return jsonify(tenant)


@tenancy_bp.put("/<tenant_id>")
def update_tenant(tenant_id: str):
    mgr, _, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    try:
        tenant = mgr.update(tenant_id, **data)
        return jsonify(tenant)
    except KeyError:
        return jsonify({"error": "테넌트 없음"}), 404


@tenancy_bp.delete("/<tenant_id>")
def deactivate_tenant(tenant_id: str):
    mgr, _, _, _ = _get_services()
    try:
        tenant = mgr.deactivate(tenant_id)
        return jsonify(tenant)
    except KeyError:
        return jsonify({"error": "테넌트 없음"}), 404


@tenancy_bp.get("/<tenant_id>/config")
def get_config(tenant_id: str):
    _, cfg, _, _ = _get_services()
    return jsonify(cfg.get(tenant_id))


@tenancy_bp.put("/<tenant_id>/config")
def set_config(tenant_id: str):
    _, cfg, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    return jsonify(cfg.set(tenant_id, **data))


@tenancy_bp.get("/<tenant_id>/usage")
def get_usage(tenant_id: str):
    _, _, usage, _ = _get_services()
    return jsonify(usage.get(tenant_id))


@tenancy_bp.get("/plans")
def list_plans():
    _, _, _, plans = _get_services()
    return jsonify(plans.list_plans())
