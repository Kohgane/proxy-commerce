"""src/api/email_marketing_api.py — 이메일 마케팅 API (Phase 88)."""
from __future__ import annotations
import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
email_marketing_bp = Blueprint("email_marketing", __name__, url_prefix="/api/v1/email-campaigns")

def _get_manager():
    from ..email_marketing import CampaignManager
    return CampaignManager()

def _get_analytics():
    from ..email_marketing import CampaignAnalytics
    return CampaignAnalytics()

def _get_unsub():
    from ..email_marketing import UnsubscribeManager
    return UnsubscribeManager()

def _get_ab():
    from ..email_marketing import ABTestCampaign
    return ABTestCampaign()

@email_marketing_bp.get("/")
def list_campaigns():
    status = request.args.get("status")
    mgr = _get_manager()
    camps = mgr.list(status)
    return jsonify([{"campaign_id": c.campaign_id, "name": c.name, "status": c.status} for c in camps])

@email_marketing_bp.post("/")
def create_campaign():
    data = request.get_json(silent=True) or {}
    mgr = _get_manager()
    c = mgr.create(
        name=data.get("name", ""),
        subject=data.get("subject", ""),
        body_template=data.get("body_template", ""),
        segment_id=data.get("segment_id", ""),
        scheduled_at=data.get("scheduled_at", ""),
    )
    return jsonify({"campaign_id": c.campaign_id, "name": c.name, "status": c.status}), 201

@email_marketing_bp.post("/<campaign_id>/send")
def send(campaign_id: str):
    data = request.get_json(silent=True) or {}
    mgr = _get_manager()
    result = mgr.send(campaign_id, recipient_count=int(data.get("recipient_count", 0)))
    return jsonify(result)

@email_marketing_bp.get("/<campaign_id>/analytics")
def analytics(campaign_id: str):
    mgr = _get_manager()
    c = mgr.get(campaign_id)
    if not c:
        return jsonify({"error": "not found"}), 404
    return jsonify(_get_analytics().stats(c))

@email_marketing_bp.post("/unsubscribe")
def unsubscribe():
    data = request.get_json(silent=True) or {}
    unsub = _get_unsub()
    result = unsub.unsubscribe(data.get("email", ""), data.get("reason", ""))
    return jsonify(result)

@email_marketing_bp.post("/ab-test")
def ab_test():
    data = request.get_json(silent=True) or {}
    ab = _get_ab()
    result = ab.create_test(
        name=data.get("name", ""),
        variant_a=data.get("variant_a", {}),
        variant_b=data.get("variant_b", {}),
        segment_id=data.get("segment_id", ""),
    )
    return jsonify(result), 201
