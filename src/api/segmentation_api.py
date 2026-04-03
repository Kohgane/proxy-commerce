"""src/api/segmentation_api.py — 고객 세그먼트 API Blueprint (Phase 73)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

segmentation_bp = Blueprint("segmentation", __name__, url_prefix="/api/v1/segments")


@segmentation_bp.get("/")
def list_segments():
    """세그먼트 목록 조회."""
    from ..segmentation import SegmentManager
    mgr = SegmentManager()
    return jsonify(mgr.list())


@segmentation_bp.post("/")
def create_segment():
    """세그먼트 생성."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify({"error": "name 필드가 필요합니다"}), 400
    from ..segmentation import SegmentManager
    mgr = SegmentManager()
    try:
        seg = mgr.create(
            name=name,
            description=body.get("description", ""),
            rules=body.get("rules", []),
            logic=body.get("logic", "AND"),
        )
        return jsonify(seg), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409


@segmentation_bp.get("/<name>")
def get_segment(name: str):
    """세그먼트 상세 조회."""
    from ..segmentation import SegmentManager
    mgr = SegmentManager()
    seg = mgr.get(name)
    if seg is None:
        return jsonify({"error": "세그먼트 없음"}), 404
    return jsonify(seg)


@segmentation_bp.put("/<name>")
def update_segment(name: str):
    """세그먼트 수정."""
    body = request.get_json(silent=True) or {}
    from ..segmentation import SegmentManager
    mgr = SegmentManager()
    try:
        seg = mgr.update(name, **body)
        return jsonify(seg)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@segmentation_bp.delete("/<name>")
def delete_segment(name: str):
    """세그먼트 삭제."""
    from ..segmentation import SegmentManager
    mgr = SegmentManager()
    try:
        mgr.delete(name)
        return jsonify({"deleted": name})
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@segmentation_bp.post("/<name>/build")
def build_segment(name: str):
    """세그먼트 자동 빌드."""
    body = request.get_json(silent=True) or {}
    customers = body.get("customers", [])
    from ..segmentation import SegmentManager
    mgr = SegmentManager()
    try:
        count = mgr.build_segment(name, customers)
        return jsonify({"segment_name": name, "matched_count": count})
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@segmentation_bp.get("/<name>/analyze")
def analyze_segment(name: str):
    """세그먼트 통계 분석."""
    from ..segmentation import SegmentManager, SegmentAnalyzer
    mgr = SegmentManager()
    seg = mgr.get(name)
    if seg is None:
        return jsonify({"error": "세그먼트 없음"}), 404
    customers_ids = mgr.get_customers(name)
    # 고객 ID만 있으므로 최소 데이터로 분석
    customers = [{"customer_id": cid} for cid in customers_ids]
    analyzer = SegmentAnalyzer()
    return jsonify(analyzer.analyze(name, customers))


@segmentation_bp.get("/<name>/export")
def export_segment(name: str):
    """세그먼트 CSV 내보내기."""
    from ..segmentation import SegmentManager, SegmentExporter
    mgr = SegmentManager()
    if mgr.get(name) is None:
        return jsonify({"error": "세그먼트 없음"}), 404
    customer_ids = mgr.get_customers(name)
    customers = [{"customer_id": cid} for cid in customer_ids]
    exporter = SegmentExporter()
    result = exporter.export_segment(name, customers)
    return jsonify(result)


@segmentation_bp.get("/<name>/customers")
def segment_customers(name: str):
    """세그먼트 고객 목록."""
    from ..segmentation import SegmentManager
    mgr = SegmentManager()
    try:
        customers = mgr.get_customers(name)
        return jsonify({"segment_name": name, "customers": customers, "count": len(customers)})
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
