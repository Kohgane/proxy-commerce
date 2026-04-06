"""src/api/source_monitor_api.py — 소싱처 실시간 모니터링 API Blueprint (Phase 108).

Blueprint: /api/v1/source-monitor

엔드포인트:
  POST /sources                        — 소싱처 상품 등록
  GET  /sources                        — 소싱처 목록
  GET  /sources/<id>                   — 소싱처 상세
  PUT  /sources/<id>                   — 소싱처 수정
  DELETE /sources/<id>                 — 소싱처 삭제
  POST /sources/<id>/check             — 즉시 상태 체크
  GET  /sources/<id>/history           — 변동 이력
  GET  /sources/<id>/alternatives      — 대체 소싱처
  POST /sources/<id>/switch            — 소싱처 전환
  GET  /changes                        — 전체 변동 이벤트
  GET  /changes/critical               — 긴급 변동만
  GET  /deactivated                    — 비활성화된 상품
  POST /deactivated/<id>/reactivate    — 재활성화
  GET  /rules                          — 비활성화 규칙
  POST /rules                          — 규칙 추가
  GET  /dashboard                      — 대시보드 데이터
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

source_monitor_bp = Blueprint(
    'source_monitor',
    __name__,
    url_prefix='/api/v1/source-monitor',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_engine = None
_detector = None
_deactivation_svc = None
_alternative_finder = None
_scheduler = None
_dashboard = None


def _get_engine():
    global _engine
    if _engine is None:
        from src.source_monitor.engine import SourceMonitorEngine
        _engine = SourceMonitorEngine()
    return _engine


def _get_detector():
    global _detector
    if _detector is None:
        from src.source_monitor.change_detector import ChangeDetector
        _detector = ChangeDetector()
    return _detector


def _get_deactivation_svc():
    global _deactivation_svc
    if _deactivation_svc is None:
        from src.source_monitor.auto_deactivation import AutoDeactivationService
        _deactivation_svc = AutoDeactivationService()
    return _deactivation_svc


def _get_alternative_finder():
    global _alternative_finder
    if _alternative_finder is None:
        from src.source_monitor.alternative_finder import AlternativeSourceFinder
        _alternative_finder = AlternativeSourceFinder()
    return _alternative_finder


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        from src.source_monitor.scheduler import SourceMonitorScheduler
        _scheduler = SourceMonitorScheduler()
    return _scheduler


def _get_dashboard():
    global _dashboard
    if _dashboard is None:
        from src.source_monitor.dashboard import SourceMonitorDashboard
        _dashboard = SourceMonitorDashboard(
            engine=_get_engine(),
            detector=_get_detector(),
            deactivation_svc=_get_deactivation_svc(),
            scheduler=_get_scheduler(),
        )
    return _dashboard


# ── 소싱처 상품 ──────────────────────────────────────────────────────────────

@source_monitor_bp.post('/sources')
def register_source():
    """소싱처 상품 등록."""
    data = request.get_json(force=True) or {}
    try:
        product = _get_engine().register_product(data)
        _get_scheduler().register(product, priority=data.get('priority', 5))
        return jsonify({'success': True, 'product': product.to_dict()}), 201
    except Exception as exc:
        logger.error("register_source 오류: %s", exc)
        return jsonify({'error': str(exc)}), 400


@source_monitor_bp.get('/sources')
def list_sources():
    """소싱처 목록."""
    status = request.args.get('status')
    try:
        products = _get_engine().list_products(status=status)
        return jsonify({
            'success': True,
            'products': [p.to_dict() for p in products],
            'total': len(products),
        })
    except Exception as exc:
        logger.error("list_sources 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@source_monitor_bp.get('/sources/<source_id>')
def get_source(source_id: str):
    """소싱처 상세."""
    product = _get_engine().get_product(source_id)
    if not product:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'success': True, 'product': product.to_dict()})


@source_monitor_bp.put('/sources/<source_id>')
def update_source(source_id: str):
    """소싱처 수정."""
    data = request.get_json(force=True) or {}
    product = _get_engine().update_product(source_id, data)
    if not product:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'success': True, 'product': product.to_dict()})


@source_monitor_bp.delete('/sources/<source_id>')
def delete_source(source_id: str):
    """소싱처 삭제."""
    ok = _get_engine().delete_product(source_id)
    if not ok:
        return jsonify({'error': 'not found'}), 404
    _get_scheduler().unregister(source_id)
    return jsonify({'success': True})


@source_monitor_bp.post('/sources/<source_id>/check')
def check_source(source_id: str):
    """즉시 상태 체크."""
    try:
        result = _get_engine().run_check(source_id)
        if 'error' in result:
            return jsonify(result), 404
        return jsonify({'success': True, **result})
    except Exception as exc:
        logger.error("check_source 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@source_monitor_bp.get('/sources/<source_id>/history')
def get_source_history(source_id: str):
    """변동 이력."""
    events = _get_detector().get_events(source_product_id=source_id)
    return jsonify({
        'success': True,
        'events': [e.to_dict() for e in events],
        'total': len(events),
    })


@source_monitor_bp.get('/sources/<source_id>/alternatives')
def get_alternatives(source_id: str):
    """대체 소싱처."""
    product = _get_engine().get_product(source_id)
    if not product:
        # 등록되지 않은 상품도 조회 시도
        alternatives = _get_alternative_finder().get_alternatives(source_id)
        return jsonify({
            'success': True,
            'alternatives': [a.to_dict() for a in alternatives],
        })
    alternatives = _get_alternative_finder().find_alternatives(product)
    return jsonify({
        'success': True,
        'alternatives': [a.to_dict() for a in alternatives],
    })


@source_monitor_bp.post('/sources/<source_id>/switch')
def switch_source(source_id: str):
    """소싱처 전환."""
    data = request.get_json(force=True) or {}
    alternative_id = data.get('alternative_id', '')
    product = _get_engine().get_product(source_id)
    if not product:
        return jsonify({'error': 'product not found'}), 404
    result = _get_alternative_finder().switch_source(product, alternative_id)
    if not result:
        return jsonify({'error': 'alternative not found or not approved'}), 400
    return jsonify({'success': True, **result})


# ── 변동 이벤트 ──────────────────────────────────────────────────────────────

@source_monitor_bp.get('/changes')
def list_changes():
    """전체 변동 이벤트."""
    severity = request.args.get('severity')
    events = _get_detector().get_events(severity=severity)
    return jsonify({
        'success': True,
        'events': [e.to_dict() for e in events],
        'total': len(events),
    })


@source_monitor_bp.get('/changes/critical')
def list_critical_changes():
    """긴급 변동 이벤트."""
    events = _get_detector().get_critical_events()
    return jsonify({
        'success': True,
        'events': [e.to_dict() for e in events],
        'total': len(events),
    })


# ── 비활성화 ─────────────────────────────────────────────────────────────────

@source_monitor_bp.get('/deactivated')
def list_deactivated():
    """비활성화된 상품 목록."""
    records = _get_deactivation_svc().list_deactivated()
    return jsonify({
        'success': True,
        'records': [r.to_dict() for r in records],
        'total': len(records),
    })


@source_monitor_bp.post('/deactivated/<record_id>/reactivate')
def reactivate_product(record_id: str):
    """재활성화."""
    ok = _get_deactivation_svc().reactivate(record_id)
    if not ok:
        return jsonify({'error': 'record not found or already active'}), 404
    return jsonify({'success': True})


# ── 비활성화 규칙 ─────────────────────────────────────────────────────────────

@source_monitor_bp.get('/rules')
def list_rules():
    """비활성화 규칙 목록."""
    rules = _get_deactivation_svc().list_rules()
    return jsonify({
        'success': True,
        'rules': [r.to_dict() for r in rules],
        'total': len(rules),
    })


@source_monitor_bp.post('/rules')
def add_rule():
    """규칙 추가."""
    data = request.get_json(force=True) or {}
    try:
        rule = _get_deactivation_svc().add_rule(data)
        return jsonify({'success': True, 'rule': rule.to_dict()}), 201
    except Exception as exc:
        logger.error("add_rule 오류: %s", exc)
        return jsonify({'error': str(exc)}), 400


# ── 대시보드 ─────────────────────────────────────────────────────────────────

@source_monitor_bp.get('/dashboard')
def get_dashboard():
    """대시보드 데이터."""
    try:
        data = _get_dashboard().get_dashboard()
        return jsonify({'success': True, **data})
    except Exception as exc:
        logger.error("get_dashboard 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500
