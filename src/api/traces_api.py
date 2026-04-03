"""src/api/traces_api.py — Phase 53: 로깅/추적 API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

traces_bp = Blueprint('traces', __name__, url_prefix='/api/v1/traces')


@traces_bp.get('/status')
def traces_status():
    return jsonify({'status': 'ok', 'module': 'logging_tracing'})


@traces_bp.get('')
def search_logs():
    from ..logging_tracing.log_aggregator import LogAggregator
    try:
        aggregator = LogAggregator()
        level = request.args.get('level')
        service = request.args.get('service')
        trace_id = request.args.get('trace_id')
        limit = int(request.args.get('limit', 100))
        logs = aggregator.get_logs(limit=limit, level=level, service=service, trace_id=trace_id)
        return jsonify(logs)
    except Exception as exc:
        logger.error("로그 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@traces_bp.get('/<trace_id>')
def get_trace(trace_id: str):
    from ..logging_tracing.log_aggregator import LogAggregator
    try:
        aggregator = LogAggregator()
        logs = aggregator.get_logs(trace_id=trace_id)
        return jsonify({'trace_id': trace_id, 'logs': logs})
    except Exception as exc:
        logger.error("추적 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
