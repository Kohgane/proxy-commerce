"""src/api/customer_segmentation_api.py — 고객 세그멘테이션 API (Phase 86)."""
from __future__ import annotations
import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
customer_segmentation_bp = Blueprint("customer_segmentation", __name__, url_prefix="/api/v1/segments")

def _get_manager():
    from ..customer_segmentation import SegmentManager
    return SegmentManager()

def _get_analyzer():
    from ..customer_segmentation import SegmentAnalyzer
    return SegmentAnalyzer()

def _get_exporter():
    from ..customer_segmentation import SegmentExporter
    return SegmentExporter()

def _get_auto():
    from ..customer_segmentation import AutoSegmenter
    return AutoSegmenter()

@customer_segmentation_bp.get("/")
def list_segments():
    mgr = _get_manager()
    return jsonify([{"segment_id": s.segment_id, "name": s.name, "customer_count": s.customer_count} for s in mgr.list()])

@customer_segmentation_bp.post("/")
def create_segment():
    data = request.get_json(silent=True) or {}
    mgr = _get_manager()
    seg = mgr.create(name=data.get("name", ""), description=data.get("description", ""), rules=data.get("rules"))
    return jsonify({"segment_id": seg.segment_id, "name": seg.name}), 201

@customer_segmentation_bp.get("/<segment_id>")
def get_segment(segment_id: str):
    mgr = _get_manager()
    seg = mgr.get(segment_id)
    if not seg:
        return jsonify({"error": "not found"}), 404
    return jsonify({"segment_id": seg.segment_id, "name": seg.name, "description": seg.description})

@customer_segmentation_bp.post("/<segment_id>/analyze")
def analyze(segment_id: str):
    data = request.get_json(silent=True) or {}
    customers = data.get("customers", [])
    analyzer = _get_analyzer()
    return jsonify(analyzer.analyze(segment_id, customers))

@customer_segmentation_bp.post("/<segment_id>/export")
def export_csv(segment_id: str):
    data = request.get_json(silent=True) or {}
    customers = data.get("customers", [])
    exporter = _get_exporter()
    csv_data = exporter.export_csv(customers)
    return jsonify({"csv": csv_data})
