"""src/api/promotions_api.py — 프로모션 관리 API.

Flask Blueprint 기반 프로모션 관리 API.

엔드포인트:
  GET  /api/promotions              — 활성 프로모션 목록
  POST /api/promotions              — 프로모션 생성
  PATCH /api/promotions/<id>        — 프로모션 수정
  GET  /api/promotions/<id>/stats   — 프로모션 성과

환경변수:
  DASHBOARD_API_KEY  — API 인증 키
  PROMOTIONS_ENABLED — 프로모션 활성화 여부
"""

import logging

from flask import Blueprint, jsonify, request

from .auth_middleware import require_api_key

logger = logging.getLogger(__name__)

promotions_bp = Blueprint("promotions", __name__, url_prefix="/api/promotions")


def _get_engine():
    """PromotionEngine 인스턴스를 반환한다."""
    from ..promotions.engine import PromotionEngine
    return PromotionEngine()


@promotions_bp.get("")
@require_api_key
def list_promotions():
    """프로모션 목록을 반환한다.

    쿼리 파라미터:
      active_only — "1" 이면 활성 프로모션만 반환 (기본 "0")
    """
    active_only = request.args.get("active_only", "0") in ("1", "true", "yes")
    engine = _get_engine()

    try:
        promos = engine.get_promotions(active_only=active_only)
    except Exception as exc:
        logger.warning("프로모션 목록 조회 실패: %s", exc)
        promos = []

    return jsonify({
        "promotions": promos,
        "count": len(promos),
        "active_only": active_only,
    })


@promotions_bp.post("")
@require_api_key
def create_promotion():
    """새 프로모션을 생성한다.

    요청 바디:
      {
        "name": "여름 할인",
        "type": "PERCENTAGE",
        "value": 10,
        "start_date": "2026-06-01T00:00:00",
        "end_date": "2026-06-30T23:59:59",
        "min_order_krw": 50000
      }
    """
    data = request.get_json(silent=True) or {}
    engine = _get_engine()

    try:
        promo = engine.create_promotion(data)
        return jsonify({"promotion": promo, "ok": True}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.error("프로모션 생성 실패: %s", exc)
        return jsonify({"error": "Internal server error"}), 500


@promotions_bp.patch("/<promo_id>")
@require_api_key
def update_promotion(promo_id: str):
    """프로모션을 수정한다.

    요청 바디:
      수정할 필드 딕셔너리 (예: {"active": "0", "end_date": "2026-07-01"})
    """
    data = request.get_json(silent=True) or {}
    engine = _get_engine()

    try:
        success = engine.update_promotion(promo_id, data)
    except Exception as exc:
        logger.error("프로모션 수정 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500

    if success:
        return jsonify({"promo_id": promo_id, "ok": True})
    return jsonify({"error": "Promotion not found", "promo_id": promo_id}), 404


@promotions_bp.get("/<promo_id>/stats")
@require_api_key
def promotion_stats(promo_id: str):
    """프로모션 성과를 반환한다."""
    engine = _get_engine()

    try:
        stats = engine.get_promo_stats(promo_id)
    except Exception as exc:
        logger.error("프로모션 성과 조회 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500

    if stats is not None:
        return jsonify(stats)
    return jsonify({"error": "Promotion not found", "promo_id": promo_id}), 404
