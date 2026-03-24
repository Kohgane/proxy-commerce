"""src/api/crm_api.py — CRM API.

Flask Blueprint 기반 CRM API.

엔드포인트:
  GET /api/customers                    — 고객 목록 (필터: segment, country)
  GET /api/customers/<email>/profile    — 고객 상세 프로필
  GET /api/customers/segments/summary   — 세그먼트별 요약

환경변수:
  DASHBOARD_API_KEY  — API 인증 키
  CRM_ENABLED        — CRM 활성화 여부
"""

import logging

from flask import Blueprint, jsonify, request

from .auth_middleware import require_api_key

logger = logging.getLogger(__name__)

crm_bp = Blueprint("crm", __name__, url_prefix="/api/customers")


def _get_profile_manager():
    """CustomerProfileManager 인스턴스를 반환한다."""
    from ..crm.customer_profile import CustomerProfileManager
    return CustomerProfileManager()


def _get_segmentation():
    """CustomerSegmentation 인스턴스를 반환한다."""
    from ..crm.segmentation import CustomerSegmentation
    return CustomerSegmentation()


@crm_bp.get("")
@require_api_key
def list_customers():
    """고객 목록을 반환한다.

    쿼리 파라미터:
      segment — 세그먼트 필터 (VIP/LOYAL/AT_RISK/NEW/DORMANT)
      country — 국가 필터 (예: KR, US)
    """
    segment = request.args.get("segment")
    country = request.args.get("country")

    manager = _get_profile_manager()
    try:
        customers = manager.get_all_customers(segment=segment, country=country)
    except Exception as exc:
        logger.warning("고객 목록 조회 실패: %s", exc)
        customers = []

    return jsonify({
        "customers": customers,
        "count": len(customers),
        "filters": {"segment": segment, "country": country},
    })


@crm_bp.get("/segments/summary")
@require_api_key
def segments_summary():
    """세그먼트별 요약 통계를 반환한다."""
    manager = _get_profile_manager()
    segmentation = _get_segmentation()

    try:
        customers = manager.get_all_customers()
        summary = segmentation.get_segment_summary(customers=customers)
    except Exception as exc:
        logger.warning("세그먼트 요약 조회 실패: %s", exc)
        from ..crm.segmentation import SEGMENTS
        summary = {seg: {"count": 0, "avg_spent_krw": 0.0, "avg_orders": 0.0} for seg in SEGMENTS}

    return jsonify({"segments": summary})


@crm_bp.get("/<path:email>/profile")
@require_api_key
def customer_profile(email: str):
    """고객 상세 프로필을 반환한다."""
    manager = _get_profile_manager()

    try:
        profile = manager.get_profile(email)
    except Exception as exc:
        logger.error("고객 프로필 조회 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500

    if profile is not None:
        segmentation = _get_segmentation()
        try:
            current_segment = segmentation.classify(profile)
            profile["computed_segment"] = current_segment
        except Exception:
            pass
        return jsonify(profile)

    return jsonify({"error": "Customer not found", "email": email}), 404
