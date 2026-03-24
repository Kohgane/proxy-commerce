"""src/api/marketing_api.py — 마케팅 API.

Flask Blueprint 기반 마케팅 캠페인 및 A/B 테스팅 API.

엔드포인트:
  GET  /api/marketing/campaigns                 — 캠페인 목록
  POST /api/marketing/campaigns                 — 캠페인 생성
  PATCH /api/marketing/campaigns/<campaign_id>  — 캠페인 업데이트/상태 변경
  GET  /api/marketing/ab-tests                  — A/B 테스트 결과 목록
  POST /api/marketing/ab-tests                  — A/B 테스트 변형 조회/생성

환경변수:
  DASHBOARD_API_KEY  — API 인증 키
"""

import logging

from flask import Blueprint, jsonify, request

from .auth_middleware import require_api_key

logger = logging.getLogger(__name__)

marketing_bp = Blueprint("marketing", __name__, url_prefix="/api/marketing")


def _get_campaign_manager():
    """CampaignManager 인스턴스를 반환한다."""
    from ..marketing.campaign_manager import CampaignManager
    return CampaignManager()


def _get_ab_manager():
    """ABTestManager 인스턴스를 반환한다."""
    from ..marketing.ab_testing import ABTestManager
    return ABTestManager()


@marketing_bp.get("/campaigns")
@require_api_key
def list_campaigns():
    """캠페인 목록을 반환한다."""
    status = request.args.get("status")
    manager = _get_campaign_manager()
    try:
        campaigns = manager.get_campaigns(status=status)
    except Exception as exc:
        logger.warning("캠페인 목록 조회 실패: %s", exc)
        campaigns = []
    return jsonify({"campaigns": campaigns, "count": len(campaigns)})


@marketing_bp.post("/campaigns")
@require_api_key
def create_campaign():
    """새 캠페인을 생성한다."""
    data = request.get_json(silent=True) or {}
    manager = _get_campaign_manager()
    try:
        campaign = manager.create_campaign(data)
    except Exception as exc:
        logger.warning("캠페인 생성 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify({"campaign": campaign}), 201


@marketing_bp.patch("/campaigns/<campaign_id>")
@require_api_key
def update_campaign(campaign_id: str):
    """캠페인 정보 또는 상태를 업데이트한다.

    body에 "action" 필드가 있으면 상태 전환을 수행한다.
    action: "pause" | "resume" | "complete"
    """
    data = request.get_json(silent=True) or {}
    manager = _get_campaign_manager()

    action = data.pop("action", None)
    try:
        if action == "pause":
            result = manager.pause_campaign(campaign_id)
        elif action == "resume":
            result = manager.resume_campaign(campaign_id)
        elif action == "complete":
            result = manager.complete_campaign(campaign_id)
        else:
            result = manager.update_campaign(campaign_id, data)
    except Exception as exc:
        logger.warning("캠페인 업데이트 실패 (%s): %s", campaign_id, exc)
        return jsonify({"error": str(exc)}), 500

    if result is None:
        return jsonify({"error": "캠페인을 찾을 수 없거나 상태 전환 불가"}), 404
    return jsonify({"campaign": result})


@marketing_bp.get("/ab-tests")
@require_api_key
def list_ab_tests():
    """A/B 테스트 결과 목록을 반환한다."""
    experiment_name = request.args.get("experiment")
    manager = _get_ab_manager()
    try:
        if experiment_name:
            results = manager.get_results(experiment_name)
        else:
            results = {}
    except Exception as exc:
        logger.warning("A/B 테스트 조회 실패: %s", exc)
        results = {}
    return jsonify({"results": results})


@marketing_bp.post("/ab-tests")
@require_api_key
def get_ab_variant():
    """A/B 테스트 변형을 반환하거나 전환을 기록한다.

    body: {
      "experiment_name": str,
      "customer_email": str,
      "action": "variant" | "impression" | "conversion",  (기본 "variant")
      "revenue": float  (action=conversion일 때 선택)
    }
    """
    data = request.get_json(silent=True) or {}
    experiment_name = data.get("experiment_name", "")
    customer_email = data.get("customer_email", "")
    action = data.get("action", "variant")

    manager = _get_ab_manager()
    try:
        if action == "variant":
            variant = manager.get_variant(experiment_name, customer_email)
            return jsonify({"variant": variant, "experiment_name": experiment_name})
        elif action == "impression":
            variant = manager.get_variant(experiment_name, customer_email)
            manager.record_impression(experiment_name, variant)
            return jsonify({"variant": variant, "recorded": "impression"})
        elif action == "conversion":
            variant = manager.get_variant(experiment_name, customer_email)
            revenue = float(data.get("revenue", 0))
            manager.record_conversion(experiment_name, variant, revenue)
            return jsonify({"variant": variant, "recorded": "conversion"})
        else:
            return jsonify({"error": f"알 수 없는 action: {action}"}), 400
    except Exception as exc:
        logger.warning("A/B 테스트 처리 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500
