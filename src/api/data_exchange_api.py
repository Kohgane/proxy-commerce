"""src/api/data_exchange_api.py — 데이터 교환 API Blueprint (Phase 68)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

data_exchange_bp = Blueprint("data_exchange", __name__, url_prefix="/api/v1/data-exchange")


@data_exchange_bp.post("/export")
def export():
    """데이터 내보내기."""
    body = request.get_json(silent=True) or {}
    data = body.get("data", [])
    format_ = body.get("format", "json")
    template_id = body.get("template_id", "")
    from ..data_exchange.export_manager import ExportManager
    mgr = ExportManager()
    return jsonify(mgr.export(data, format_=format_, template_id=template_id))


@data_exchange_bp.post("/import")
def import_data():
    """데이터 가져오기."""
    body = request.get_json(silent=True) or {}
    content = body.get("content", "[]")
    format_ = body.get("format", "json")
    from ..data_exchange.import_manager import ImportManager
    mgr = ImportManager()
    return jsonify(mgr.import_data(content, format_=format_))


@data_exchange_bp.get("/templates")
def templates():
    """내보내기 템플릿 목록."""
    from ..data_exchange.export_template import ExportTemplate
    tmpl = ExportTemplate()
    return jsonify(tmpl.list_templates())


@data_exchange_bp.get("/status/<job_id>")
def job_status(job_id: str):
    """대량 작업 상태 조회."""
    from ..data_exchange.bulk_operation import BulkOperation
    bulk = BulkOperation()
    status = bulk.get_status(job_id)
    if not status:
        return jsonify({"error": "job not found"}), 404
    return jsonify(status)
