"""src/api/rate_limits_api.py — 레이트 리미팅 API Blueprint (Phase 62)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

rate_limits_bp = Blueprint("rate_limits", __name__, url_prefix="/api/v1/rate-limits")

_policy = None
_limiter = None
_dashboard = None


def _get_services():
    global _policy, _limiter, _dashboard
    if _policy is None:
        from ..rate_limiting.sliding_window_limiter import SlidingWindowLimiter
        from ..rate_limiting.rate_limit_policy import RateLimitPolicy
        from ..rate_limiting.rate_limit_dashboard import RateLimitDashboard
        _limiter = SlidingWindowLimiter()
        _policy = RateLimitPolicy()
        _dashboard = RateLimitDashboard(limiter=_limiter, policy=_policy)
    return _policy, _limiter, _dashboard


@rate_limits_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "rate_limits"})


@rate_limits_bp.get("/policies")
def list_policies():
    policy, _, _ = _get_services()
    return jsonify({"policies": policy.list_policies()})


@rate_limits_bp.post("/policies")
def create_policy():
    policy, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    endpoint = data.get("endpoint", "")
    limit = data.get("limit", 100)
    window = data.get("window", 60)
    if not endpoint:
        return jsonify({"error": "endpoint 필요"}), 400
    p = policy.set_policy(endpoint, limit, window)
    return jsonify(p), 201


@rate_limits_bp.get("/usage")
def get_usage():
    _, _, dashboard = _get_services()
    return jsonify({"usage": dashboard.get_usage_all()})


@rate_limits_bp.get("/stats")
def get_stats():
    _, _, dashboard = _get_services()
    return jsonify(dashboard.get_stats())
