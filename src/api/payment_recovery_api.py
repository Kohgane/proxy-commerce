"""src/api/payment_recovery_api.py — 결제 복구 API (Phase 82)."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

payment_recovery_bp = Blueprint("payment_recovery", __name__, url_prefix="/api/v1/payment-recovery")


@payment_recovery_bp.get("/failures")
def list_failures():
    """결제 실패 목록을 반환한다."""
    from ..payment_recovery import PaymentRecoveryManager
    return jsonify(PaymentRecoveryManager().list_failures())


@payment_recovery_bp.post("/retry")
def retry():
    """결제를 재시도한다."""
    from ..payment_recovery import PaymentRecoveryManager
    data = request.get_json(silent=True) or {}
    mgr = PaymentRecoveryManager()
    payment_id = data.get('payment_id', '')
    try:
        result = mgr.retry(payment_id)
        return jsonify(result)
    except KeyError:
        return jsonify({'error': 'Payment not found'}), 404


@payment_recovery_bp.post("/dunning")
def dunning():
    """독촉을 발송한다."""
    from ..payment_recovery import DunningManager
    data = request.get_json(silent=True) or {}
    mgr = DunningManager()
    result = mgr.send_dunning(
        payment_id=data.get('payment_id', ''),
        level=int(data.get('level', 1)),
    )
    return jsonify(result)


@payment_recovery_bp.get("/report")
def report():
    """복구 보고서를 반환한다."""
    from ..payment_recovery import RecoveryReport
    return jsonify(RecoveryReport().generate())


@payment_recovery_bp.post("/fallback")
def fallback():
    """대안 결제 수단을 제안한다."""
    from ..payment_recovery import PaymentFallback
    data = request.get_json(silent=True) or {}
    fb = PaymentFallback()
    alternatives = fb.suggest_alternatives(data.get('error_code', 'DEFAULT'))
    return jsonify({'alternatives': alternatives})
