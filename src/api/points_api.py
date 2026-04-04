"""src/api/points_api.py — 포인트/마일리지 API Blueprint (Phase 92).

Blueprint: /api/v1/points

엔드포인트:
  GET  /<user_id>/balance    — 포인트 잔액 조회
  POST /<user_id>/earn       — 포인트 적립
  POST /<user_id>/use        — 포인트 사용
  GET  /<user_id>/history    — 이력 조회 (타입/기간 필터)
  GET  /<user_id>/expiring   — 만료 예정 포인트
  POST /expire/run           — 만료 배치 실행
  GET  /policy               — 적립 정책 조회
  PUT  /policy               — 적립 정책 수정
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

points_bp = Blueprint("points", __name__, url_prefix="/api/v1/points")

_manager = None
_expiry = None


def _get_services():
    """서비스 인스턴스를 반환한다 (지연 초기화)."""
    global _manager, _expiry
    if _manager is None:
        from ..points.point_manager import PointManager
        from ..points.expiry_manager import ExpiryManager
        _manager = PointManager()
        _expiry = ExpiryManager(point_manager=_manager, history=_manager.history)
    return _manager, _expiry


# ---------------------------------------------------------------------------
# 잔액 조회
# ---------------------------------------------------------------------------

@points_bp.get("/<user_id>/balance")
def get_balance(user_id: str):
    """포인트 잔액을 조회한다."""
    mgr, _ = _get_services()
    balance = mgr.get_balance(user_id)
    return jsonify({"user_id": user_id, "balance": balance})


# ---------------------------------------------------------------------------
# 포인트 적립
# ---------------------------------------------------------------------------

@points_bp.post("/<user_id>/earn")
def earn_points(user_id: str):
    """포인트를 적립한다."""
    mgr, _ = _get_services()
    data = request.get_json(silent=True) or {}

    amount = data.get("amount")
    reason = data.get("reason", "")
    if amount is None or not reason:
        return jsonify({"error": "필수 필드 누락: amount, reason"}), 400

    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "amount는 정수여야 합니다."}), 400

    order_id = data.get("order_id")
    try:
        lot = mgr.earn(user_id=user_id, amount=amount, reason=reason, order_id=order_id)
        return jsonify({"lot": lot.to_dict(), "balance": mgr.get_balance(user_id)}), 201
    except ValueError:
        return jsonify({"error": "포인트 적립에 실패했습니다."}), 400


# ---------------------------------------------------------------------------
# 포인트 사용
# ---------------------------------------------------------------------------

@points_bp.post("/<user_id>/use")
def use_points(user_id: str):
    """포인트를 사용한다."""
    mgr, _ = _get_services()
    data = request.get_json(silent=True) or {}

    use_amount = data.get("use_amount")
    payment_amount = data.get("payment_amount")
    reason = data.get("reason", "")

    if use_amount is None or payment_amount is None or not reason:
        return jsonify({"error": "필수 필드 누락: use_amount, payment_amount, reason"}), 400

    try:
        use_amount = int(use_amount)
        payment_amount = int(payment_amount)
    except (ValueError, TypeError):
        return jsonify({"error": "use_amount, payment_amount는 정수여야 합니다."}), 400

    order_id = data.get("order_id")
    try:
        deducted = mgr.use(
            user_id=user_id,
            use_amount=use_amount,
            payment_amount=payment_amount,
            reason=reason,
            order_id=order_id,
        )
        return jsonify({"deducted": deducted, "balance": mgr.get_balance(user_id)})
    except ValueError:
        return jsonify({"error": "포인트 사용에 실패했습니다."}), 400


# ---------------------------------------------------------------------------
# 이력 조회
# ---------------------------------------------------------------------------

@points_bp.get("/<user_id>/history")
def get_history(user_id: str):
    """포인트 이력을 조회한다."""
    mgr, _ = _get_services()
    history_type = request.args.get("type")
    since = request.args.get("since")
    until = request.args.get("until")
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
    except ValueError:
        return jsonify({"error": "page, per_page는 정수여야 합니다."}), 400

    result = mgr.history.query(
        user_id=user_id,
        history_type=history_type,
        since=since,
        until=until,
        page=page,
        per_page=per_page,
    )
    return jsonify(result)


# ---------------------------------------------------------------------------
# 만료 예정 포인트
# ---------------------------------------------------------------------------

@points_bp.get("/<user_id>/expiring")
def get_expiring(user_id: str):
    """만료 예정 포인트를 조회한다."""
    _, expiry = _get_services()
    try:
        within_days = int(request.args.get("within_days", 30))
    except ValueError:
        return jsonify({"error": "within_days는 정수여야 합니다."}), 400

    lots = expiry.get_expiring_lots(user_id=user_id, within_days=within_days)
    return jsonify({"user_id": user_id, "within_days": within_days, "expiring_lots": lots})


# ---------------------------------------------------------------------------
# 만료 배치 실행
# ---------------------------------------------------------------------------

@points_bp.post("/expire/run")
def run_expire():
    """만료 배치를 실행한다."""
    _, expiry = _get_services()
    result = expiry.run_expiry_batch()
    return jsonify(result)


# ---------------------------------------------------------------------------
# 정책 조회/수정
# ---------------------------------------------------------------------------

@points_bp.get("/policy")
def get_policy():
    """적립 정책을 조회한다."""
    mgr, _ = _get_services()
    return jsonify(mgr.policy.to_dict())


@points_bp.put("/policy")
def update_policy():
    """적립 정책을 수정한다."""
    mgr, _ = _get_services()
    data = request.get_json(silent=True) or {}

    rates = data.get("rates", {})
    errors = []
    for grade, rate in rates.items():
        try:
            mgr.policy.set_rate(grade, float(rate))
        except (ValueError, TypeError):
            errors.append(f"{grade}: 유효하지 않은 적립률")

    if errors:
        return jsonify({"error": "일부 항목 수정 실패", "details": errors}), 400

    return jsonify(mgr.policy.to_dict())
