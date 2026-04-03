"""src/api/traces_api.py — 분산 추적 API Blueprint (Phase 53)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

traces_bp = Blueprint("traces", __name__, url_prefix="/api/v1/traces")

_aggregator = None
_logger = None


def _get_services():
    global _aggregator, _logger
    if _aggregator is None:
        from ..logging_tracing.log_aggregator import LogAggregator
        from ..logging_tracing.structured_logger import StructuredLogger
        _aggregator = LogAggregator()
        _logger = StructuredLogger()
    return _aggregator, _logger


@traces_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "logging_tracing"})


@traces_bp.get("/")
def search_traces():
    aggregator, _ = _get_services()
    trace_id = request.args.get("trace_id")
    level = request.args.get("level")
    keyword = request.args.get("keyword")
    limit = int(request.args.get("limit", 100))
    results = aggregator.search(trace_id=trace_id, level=level,
                                keyword=keyword, limit=limit)
    return jsonify(results)


@traces_bp.get("/<trace_id>")
def get_trace(trace_id: str):
    aggregator, _ = _get_services()
    logs = aggregator.get_by_trace(trace_id)
    if not logs:
        return jsonify({"error": "트레이스 없음"}), 404
    return jsonify({"trace_id": trace_id, "logs": logs})


@traces_bp.get("/recent")
def recent_traces():
    aggregator, _ = _get_services()
    n = int(request.args.get("n", 50))
    return jsonify(aggregator.recent(n=n))


@traces_bp.get("/stats")
def stats():
    aggregator, _ = _get_services()
    return jsonify({"total_logs": aggregator.count()})
