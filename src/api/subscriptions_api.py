"""src/api/subscriptions_api.py — 구독 결제 관리 API Blueprint (Phase 92).

Blueprint: /api/v1/subscriptions

엔드포인트:
  POST /                          — 구독 생성
  GET  /<subscription_id>         — 구독 상세
  PUT  /<subscription_id>/plan    — 플랜 변경
  POST /<subscription_id>/cancel  — 구독 취소
  GET  /<subscription_id>/invoices — 청구서 목록
  GET  /plans                     — 플랜 목록
  GET  /<subscription_id>/usage   — 사용량 현황
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

subscriptions_bp = Blueprint("subscriptions", __name__, url_prefix="/api/v1/subscriptions")

_sub_mgr = None
_plan_mgr = None
_billing = None
_limiter = None


def _get_services():
    """서비스 인스턴스를 반환한다 (지연 초기화)."""
    global _sub_mgr, _plan_mgr, _billing, _limiter
    if _sub_mgr is None:
        from ..subscriptions.subscription_manager import SubscriptionManager
        from ..subscriptions.plan_manager import PlanManager
        from ..subscriptions.billing import BillingService
        from ..subscriptions.usage_limiter import UsageLimiter
        _plan_mgr = PlanManager()
        _sub_mgr = SubscriptionManager()
        _billing = BillingService(plan_manager=_plan_mgr)
        _limiter = UsageLimiter(plan_manager=_plan_mgr)
    return _sub_mgr, _plan_mgr, _billing, _limiter


# ---------------------------------------------------------------------------
# 플랜 목록
# ---------------------------------------------------------------------------

@subscriptions_bp.get("/plans")
def list_plans():
    """플랜 목록을 조회한다."""
    _, plan_mgr, _, _ = _get_services()
    billing_cycle = request.args.get("billing_cycle", "monthly")
    plans = [p.to_dict(billing_cycle=billing_cycle) for p in plan_mgr.list_plans()]
    return jsonify({"plans": plans})


# ---------------------------------------------------------------------------
# 구독 생성
# ---------------------------------------------------------------------------

@subscriptions_bp.post("/")
def create_subscription():
    """구독을 생성한다."""
    sub_mgr, plan_mgr, billing, _ = _get_services()
    data = request.get_json(silent=True) or {}

    required = ("tenant_id", "user_id", "plan_id")
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"필수 필드 누락: {', '.join(missing)}"}), 400

    plan_id = data["plan_id"]
    if not plan_mgr.is_valid_plan(plan_id):
        return jsonify({"error": "유효하지 않은 플랜 ID입니다."}), 400

    billing_cycle = data.get("billing_cycle", "monthly")
    start_trial = data.get("start_trial", True)

    try:
        sub = sub_mgr.create(
            tenant_id=data["tenant_id"],
            user_id=data["user_id"],
            plan_id=plan_id,
            billing_cycle=billing_cycle,
            start_trial=bool(start_trial),
        )
        # 무료 플랜이 아닌 경우 청구서 생성
        invoice = None
        if plan_id != "free":
            try:
                invoice = billing.create_invoice(
                    subscription_id=sub.subscription_id,
                    user_id=data["user_id"],
                    plan_id=plan_id,
                    billing_cycle=billing_cycle,
                )
            except Exception as exc:
                logger.warning("청구서 생성 실패: %s", exc)

        return jsonify({
            "subscription": sub.to_dict(),
            "invoice": invoice.to_dict() if invoice else None,
        }), 201
    except ValueError:
        return jsonify({"error": "구독 생성에 실패했습니다."}), 400


# ---------------------------------------------------------------------------
# 구독 상세 조회
# ---------------------------------------------------------------------------

@subscriptions_bp.get("/<subscription_id>")
def get_subscription(subscription_id: str):
    """구독 상세를 조회한다."""
    sub_mgr, *_ = _get_services()
    sub = sub_mgr.get(subscription_id)
    if sub is None:
        return jsonify({"error": "구독을 찾을 수 없습니다."}), 404
    return jsonify(sub.to_dict())


# ---------------------------------------------------------------------------
# 플랜 변경
# ---------------------------------------------------------------------------

@subscriptions_bp.put("/<subscription_id>/plan")
def change_plan(subscription_id: str):
    """플랜을 변경한다."""
    sub_mgr, plan_mgr, _, _ = _get_services()
    data = request.get_json(silent=True) or {}
    new_plan_id = data.get("plan_id")
    if not new_plan_id:
        return jsonify({"error": "필수 필드 누락: plan_id"}), 400
    if not plan_mgr.is_valid_plan(new_plan_id):
        return jsonify({"error": "유효하지 않은 플랜 ID입니다."}), 400

    billing_cycle = data.get("billing_cycle")
    try:
        sub = sub_mgr.change_plan(subscription_id, new_plan_id, billing_cycle)
        return jsonify(sub.to_dict())
    except ValueError:
        return jsonify({"error": "플랜 변경에 실패했습니다."}), 400


# ---------------------------------------------------------------------------
# 구독 취소
# ---------------------------------------------------------------------------

@subscriptions_bp.post("/<subscription_id>/cancel")
def cancel_subscription(subscription_id: str):
    """구독을 취소한다."""
    sub_mgr, *_ = _get_services()
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "")
    try:
        sub = sub_mgr.cancel(subscription_id, reason=reason)
        return jsonify(sub.to_dict())
    except ValueError:
        return jsonify({"error": "구독 취소에 실패했습니다."}), 400


# ---------------------------------------------------------------------------
# 청구서 목록
# ---------------------------------------------------------------------------

@subscriptions_bp.get("/<subscription_id>/invoices")
def list_invoices(subscription_id: str):
    """구독의 청구서 목록을 조회한다."""
    sub_mgr, _, billing, _ = _get_services()
    sub = sub_mgr.get(subscription_id)
    if sub is None:
        return jsonify({"error": "구독을 찾을 수 없습니다."}), 404
    invoices = billing.list_invoices(subscription_id)
    return jsonify({"invoices": [i.to_dict() for i in invoices]})


# ---------------------------------------------------------------------------
# 사용량 현황
# ---------------------------------------------------------------------------

@subscriptions_bp.get("/<subscription_id>/usage")
def get_usage(subscription_id: str):
    """사용량 현황을 조회한다."""
    sub_mgr, _, _, limiter = _get_services()
    sub = sub_mgr.get(subscription_id)
    if sub is None:
        return jsonify({"error": "구독을 찾을 수 없습니다."}), 404
    dashboard = limiter.get_dashboard(tenant_id=sub.tenant_id, plan_id=sub.plan_id)
    return jsonify(dashboard)
