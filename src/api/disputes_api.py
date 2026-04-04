"""src/api/disputes_api.py — 분쟁 관리 API Blueprint (Phase 91).

Blueprint: /api/v1/disputes

엔드포인트:
  POST /                         — 분쟁 생성
  GET  /                         — 분쟁 목록 (상태/타입 필터)
  GET  /<dispute_id>             — 분쟁 상세
  PUT  /<dispute_id>/status      — 상태 변경
  POST /<dispute_id>/evidence    — 증거 첨부
  GET  /<dispute_id>/evidence    — 증거 목록
  POST /<dispute_id>/mediate     — 자동 중재 실행
  GET  /analytics                — 분쟁 분석 통계
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

disputes_bp = Blueprint("disputes", __name__, url_prefix="/api/v1/disputes")

_manager = None
_evidence = None
_mediation = None
_refund = None
_analytics = None


def _get_services():
    """서비스 인스턴스를 반환한다 (지연 초기화)."""
    global _manager, _evidence, _mediation, _refund, _analytics
    if _manager is None:
        from ..disputes.dispute_manager import DisputeManager
        from ..disputes.evidence import EvidenceCollector
        from ..disputes.mediation import MediationService
        from ..disputes.refund_decision import RefundDecision
        from ..disputes.analytics import DisputeAnalytics
        _manager = DisputeManager()
        _evidence = EvidenceCollector()
        _mediation = MediationService()
        _refund = RefundDecision()
        _analytics = DisputeAnalytics()
    return _manager, _evidence, _mediation, _refund, _analytics


@disputes_bp.post("/")
def create_dispute():
    """분쟁을 생성한다."""
    mgr, *_ = _get_services()
    data = request.get_json(silent=True) or {}
    required = ("order_id", "customer_id", "reason", "dispute_type")
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"필수 필드 누락: {', '.join(missing)}"}), 400
    try:
        dispute = mgr.create(
            order_id=data["order_id"],
            customer_id=data["customer_id"],
            reason=data["reason"],
            dispute_type=data["dispute_type"],
            amount=float(data.get("amount", 0)),
            notes=data.get("notes", ""),
        )
        return jsonify(dispute.to_dict()), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@disputes_bp.get("/")
def list_disputes():
    """분쟁 목록을 조회한다."""
    mgr, *_ = _get_services()
    status = request.args.get("status")
    dispute_type = request.args.get("type")
    customer_id = request.args.get("customer_id")
    disputes = mgr.list(status=status, dispute_type=dispute_type, customer_id=customer_id)
    return jsonify([d.to_dict() for d in disputes])


@disputes_bp.get("/<dispute_id>")
def get_dispute(dispute_id: str):
    """분쟁 상세를 조회한다."""
    mgr, *_ = _get_services()
    dispute = mgr.get(dispute_id)
    if not dispute:
        return jsonify({"error": "분쟁을 찾을 수 없습니다."}), 404
    return jsonify(dispute.to_dict())


@disputes_bp.put("/<dispute_id>/status")
def update_status(dispute_id: str):
    """분쟁 상태를 변경한다."""
    mgr, *_ = _get_services()
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not new_status:
        return jsonify({"error": "status 필드가 필요합니다."}), 400
    try:
        dispute = mgr.transition(dispute_id, new_status, notes=data.get("notes", ""))
        return jsonify(dispute.to_dict())
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@disputes_bp.post("/<dispute_id>/evidence")
def add_evidence(dispute_id: str):
    """증거를 첨부한다."""
    mgr, ev_col, *_ = _get_services()
    # dispute 존재 확인
    if not mgr.get(dispute_id):
        return jsonify({"error": "분쟁을 찾을 수 없습니다."}), 404
    data = request.get_json(silent=True) or {}
    required = ("evidence_type", "file_name")
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"필수 필드 누락: {', '.join(missing)}"}), 400
    try:
        evidence = ev_col.add(
            dispute_id=dispute_id,
            evidence_type=data["evidence_type"],
            file_name=data["file_name"],
            file_type=data.get("file_type", "application/octet-stream"),
            file_size=int(data.get("file_size", 0)),
            description=data.get("description", ""),
            url=data.get("url", ""),
        )
        mgr.add_evidence(dispute_id, evidence.evidence_id)
        return jsonify(evidence.to_dict()), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@disputes_bp.get("/<dispute_id>/evidence")
def list_evidence(dispute_id: str):
    """증거 목록을 조회한다."""
    mgr, ev_col, *_ = _get_services()
    if not mgr.get(dispute_id):
        return jsonify({"error": "분쟁을 찾을 수 없습니다."}), 404
    evidences = ev_col.list(dispute_id)
    return jsonify([e.to_dict() for e in evidences])


@disputes_bp.post("/<dispute_id>/mediate")
def mediate(dispute_id: str):
    """자동 중재를 실행한다."""
    mgr, ev_col, med, *_ = _get_services()
    dispute = mgr.get(dispute_id)
    if not dispute:
        return jsonify({"error": "분쟁을 찾을 수 없습니다."}), 404
    data = request.get_json(silent=True) or {}
    shipping_delay = int(data.get("shipping_delay_days", 0))
    has_photo = ev_col.has_photo_evidence(dispute_id)
    decision = med.mediate(
        dispute_id=dispute_id,
        amount=dispute.amount,
        dispute_type=dispute.dispute_type.value,
        shipping_delay_days=shipping_delay,
        has_photo_evidence=has_photo,
    )
    return jsonify(decision.to_dict())


@disputes_bp.get("/analytics")
def analytics():
    """분쟁 분석 통계를 반환한다."""
    mgr, _, __, ___, ana = _get_services()
    total_orders = int(request.args.get("total_orders", 0))
    disputes = mgr.list()
    return jsonify(ana.summary(disputes, total_orders))
