"""src/api/audit_api.py — Phase 41: 감사 로그 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

audit_bp = Blueprint('audit_v2', __name__, url_prefix='/api/v1/audit')

# 인메모리 스토어 (Blueprint 생명주기 동안 공유)
_store = None


def _get_store():
    global _store
    if _store is None:
        from ..audit.audit_store import AuditStore
        _store = AuditStore()
    return _store


@audit_bp.get('/status')
def audit_status():
    return jsonify({'status': 'ok', 'module': 'audit', 'records': _get_store().count()})


@audit_bp.get('/')
def list_audit_logs():
    """GET /api/v1/audit/ — 감사 로그 목록 (페이지네이션)."""
    from ..audit.audit_query import AuditQuery
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    event_type = request.args.get('event_type')
    user_id = request.args.get('user_id')
    resource = request.args.get('resource')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    try:
        query = AuditQuery(store=_get_store())
        result = query.query(
            start_time=start_time,
            end_time=end_time,
            user_id=user_id,
            event_type=event_type,
            resource=resource,
            page=page,
            per_page=per_page,
        )
        return jsonify(result)
    except Exception as exc:
        logger.error("감사 로그 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@audit_bp.post('/')
def create_audit_log():
    """POST /api/v1/audit/ — 감사 로그 직접 기록."""
    from ..audit.audit_logger import AuditLogger
    from ..audit.event_types import EventType
    body = request.get_json(silent=True) or {}
    event_type_str = body.get('event_type', '')
    actor = body.get('actor', 'api')
    resource = body.get('resource', '')
    details = body.get('details', {})
    ip_address = body.get('ip_address', request.remote_addr or '')
    if not event_type_str:
        return jsonify({'error': 'event_type is required'}), 400
    try:
        # event_type을 EventType enum으로 변환 시도
        try:
            et = EventType(event_type_str)
        except ValueError:
            # 문자열 그대로 사용
            et = event_type_str
        audit_logger = AuditLogger(sheet_id='')
        entry = audit_logger._build_entry(et, actor, resource, details, ip_address)
        _get_store().append(entry)
        return jsonify(entry), 201
    except Exception as exc:
        logger.error("감사 로그 기록 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@audit_bp.get('/search')
def search_audit_logs():
    """GET /api/v1/audit/search?q=keyword — 전문 검색."""
    from ..audit.audit_query import AuditQuery
    keyword = request.args.get('q', '')
    if not keyword:
        return jsonify({'error': 'q (keyword) is required'}), 400
    try:
        query = AuditQuery(store=_get_store())
        results = query.search(keyword)
        return jsonify({'items': results, 'total': len(results)})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@audit_bp.get('/recent')
def recent_audit_logs():
    """GET /api/v1/audit/recent?n=50 — 최근 N개."""
    n = int(request.args.get('n', 50))
    try:
        records = _get_store().get_recent(n)
        return jsonify({'items': records, 'total': len(records)})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
