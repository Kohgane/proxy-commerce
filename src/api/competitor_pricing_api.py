"""src/api/competitor_pricing_api.py — 경쟁사 가격 모니터링 API Blueprint (Phase 111).

Blueprint: /api/v1/competitor-pricing
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

competitor_pricing_bp = Blueprint(
    'competitor_pricing',
    __name__,
    url_prefix='/api/v1/competitor-pricing',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_tracker = None
_matcher = None
_analyzer = None
_adjuster = None
_rules = None
_alerts = None
_dashboard = None
_scheduler = None


def _get_tracker():
    global _tracker
    if _tracker is None:
        from src.competitor_pricing.tracker import CompetitorTracker
        _tracker = CompetitorTracker()
    return _tracker


def _get_matcher():
    global _matcher
    if _matcher is None:
        from src.competitor_pricing.matcher import CompetitorMatcher
        _matcher = CompetitorMatcher(_get_tracker())
    return _matcher


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer
        _analyzer = PricePositionAnalyzer(_get_tracker())
    return _analyzer


def _get_adjuster():
    global _adjuster
    if _adjuster is None:
        from src.competitor_pricing.adjuster import PriceAdjustmentSuggester
        _adjuster = PriceAdjustmentSuggester(_get_tracker(), _get_analyzer())
    return _adjuster


def _get_rules():
    global _rules
    if _rules is None:
        from src.competitor_pricing.price_rules import CompetitorPriceRules
        _rules = CompetitorPriceRules()
    return _rules


def _get_alerts():
    global _alerts
    if _alerts is None:
        from src.competitor_pricing.competitor_alerts import CompetitorAlertService
        _alerts = CompetitorAlertService(_get_tracker())
    return _alerts


def _get_dashboard():
    global _dashboard
    if _dashboard is None:
        from src.competitor_pricing.competitor_dashboard import CompetitorDashboard
        _dashboard = CompetitorDashboard(_get_tracker(), _get_analyzer(), _get_adjuster())
    return _dashboard


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        from src.competitor_pricing.competitor_scheduler import CompetitorCheckScheduler
        _scheduler = CompetitorCheckScheduler()
    return _scheduler


def _to_dict(obj: Any) -> Any:
    """dataclass 또는 일반 객체를 dict 로 변환."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        raw = dataclasses.asdict(obj)
        # Enum 값을 문자열로 변환
        return _convert_enums(raw)
    return obj


def _convert_enums(obj: Any) -> Any:
    from enum import Enum
    if isinstance(obj, dict):
        return {k: _convert_enums(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_enums(i) for i in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj


# ══════════════════════════════════════════════════════════════════════════════
# 경쟁사 관리
# ══════════════════════════════════════════════════════════════════════════════

@competitor_pricing_bp.post('/competitors')
def add_competitor():
    data = request.get_json(force=True) or {}
    try:
        product = _get_tracker().add_competitor(data)
        return jsonify({'ok': True, 'competitor': _to_dict(product)}), 201
    except Exception as exc:
        logger.error("add_competitor 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 400


@competitor_pricing_bp.get('/competitors')
def list_competitors():
    my_product_id = request.args.get('my_product_id')
    try:
        competitors = _get_tracker().get_competitors(my_product_id=my_product_id)
        return jsonify({'ok': True, 'competitors': [_to_dict(c) for c in competitors]})
    except Exception as exc:
        logger.error("list_competitors 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.get('/competitors/<competitor_id>')
def get_competitor(competitor_id: str):
    try:
        product = _get_tracker().get_competitor(competitor_id)
        if product is None:
            return jsonify({'error': '경쟁사 없음'}), 404
        return jsonify({'ok': True, 'competitor': _to_dict(product)})
    except Exception as exc:
        logger.error("get_competitor 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.delete('/competitors/<competitor_id>')
def remove_competitor(competitor_id: str):
    try:
        removed = _get_tracker().remove_competitor(competitor_id)
        if not removed:
            return jsonify({'error': '경쟁사 없음'}), 404
        return jsonify({'ok': True})
    except Exception as exc:
        logger.error("remove_competitor 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.post('/competitors/<competitor_id>/check')
def check_competitor(competitor_id: str):
    try:
        product = _get_tracker().check_competitor(competitor_id)
        if product is None:
            return jsonify({'error': '가격 체크 실패'}), 500
        return jsonify({'ok': True, 'competitor': _to_dict(product)})
    except Exception as exc:
        logger.error("check_competitor 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.get('/competitors/<competitor_id>/history')
def get_price_history(competitor_id: str):
    period = request.args.get('period')
    try:
        history = _get_tracker().get_price_history(competitor_id, period=period)
        return jsonify({'ok': True, 'history': history})
    except Exception as exc:
        logger.error("get_price_history 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ══════════════════════════════════════════════════════════════════════════════
# 매칭
# ══════════════════════════════════════════════════════════════════════════════

@competitor_pricing_bp.post('/match/<my_product_id>')
def find_competitors(my_product_id: str):
    data = request.get_json(force=True) or {}
    try:
        matches = _get_matcher().find_competitors(
            my_product_id,
            my_product=data,
            platforms=data.get('platforms'),
        )
        return jsonify({'ok': True, 'matches': [_to_dict(m) for m in matches]}), 201
    except Exception as exc:
        logger.error("find_competitors 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 400


@competitor_pricing_bp.get('/matches')
def list_matches():
    my_product_id = request.args.get('my_product_id')
    try:
        matches = _get_matcher().get_matches(my_product_id=my_product_id)
        return jsonify({'ok': True, 'matches': [_to_dict(m) for m in matches]})
    except Exception as exc:
        logger.error("list_matches 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.post('/matches/<match_id>/confirm')
def confirm_match(match_id: str):
    try:
        ok = _get_matcher().confirm_match(match_id)
        if not ok:
            return jsonify({'error': '매칭 없음'}), 404
        return jsonify({'ok': True})
    except Exception as exc:
        logger.error("confirm_match 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.post('/matches/<match_id>/reject')
def reject_match(match_id: str):
    try:
        ok = _get_matcher().reject_match(match_id)
        if not ok:
            return jsonify({'error': '매칭 없음'}), 404
        return jsonify({'ok': True})
    except Exception as exc:
        logger.error("reject_match 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ══════════════════════════════════════════════════════════════════════════════
# 포지션 분석
# ══════════════════════════════════════════════════════════════════════════════

@competitor_pricing_bp.get('/position/<my_product_id>')
def analyze_position(my_product_id: str):
    channel = request.args.get('channel')
    try:
        position = _get_analyzer().analyze_position(my_product_id, channel=channel)
        return jsonify({'ok': True, 'position': _to_dict(position)})
    except Exception as exc:
        logger.error("analyze_position 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.get('/position/all')
def analyze_all_positions():
    channel = request.args.get('channel')
    try:
        positions = _get_analyzer().analyze_all_positions(channel=channel)
        return jsonify({'ok': True, 'positions': {k: _to_dict(v) for k, v in positions.items()}})
    except Exception as exc:
        logger.error("analyze_all_positions 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.get('/position/summary')
def position_summary():
    try:
        summary = _get_analyzer().get_position_summary()
        return jsonify({'ok': True, 'summary': summary})
    except Exception as exc:
        logger.error("position_summary 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.get('/position/<my_product_id>/distribution')
def price_distribution(my_product_id: str):
    try:
        dist = _get_analyzer().get_price_distribution(my_product_id)
        return jsonify({'ok': True, 'distribution': dist})
    except Exception as exc:
        logger.error("price_distribution 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ══════════════════════════════════════════════════════════════════════════════
# 가격 조정 제안
# ══════════════════════════════════════════════════════════════════════════════

@competitor_pricing_bp.post('/suggest/<my_product_id>')
def suggest_adjustment(my_product_id: str):
    data = request.get_json(force=True) or {}
    try:
        from src.competitor_pricing.adjuster import AdjustmentStrategy
        strategy_str = data.get('strategy')
        strategy = AdjustmentStrategy(strategy_str) if strategy_str else None
        suggestion = _get_adjuster().suggest_adjustment(
            my_product_id, strategy=strategy, channel=data.get('channel')
        )
        if suggestion is None:
            return jsonify({'ok': False, 'message': '제안 생성 불가'}), 400
        return jsonify({'ok': True, 'suggestion': _to_dict(suggestion)}), 201
    except Exception as exc:
        logger.error("suggest_adjustment 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 400


@competitor_pricing_bp.post('/suggest/bulk')
def suggest_bulk():
    data = request.get_json(force=True) or {}
    try:
        from src.competitor_pricing.adjuster import AdjustmentStrategy
        strategy_str = data.get('strategy')
        strategy = AdjustmentStrategy(strategy_str) if strategy_str else None
        suggestions = _get_adjuster().suggest_bulk_adjustments(
            strategy=strategy, channel=data.get('channel')
        )
        return jsonify({'ok': True, 'suggestions': [_to_dict(s) for s in suggestions]}), 201
    except Exception as exc:
        logger.error("suggest_bulk 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 400


@competitor_pricing_bp.get('/suggestions')
def list_suggestions():
    status_str = request.args.get('status')
    strategy_str = request.args.get('strategy')
    try:
        from src.competitor_pricing.adjuster import AdjustmentStrategy, SuggestionStatus
        status = SuggestionStatus(status_str) if status_str else None
        strategy = AdjustmentStrategy(strategy_str) if strategy_str else None
        suggestions = _get_adjuster().get_suggestions(status=status, strategy=strategy)
        return jsonify({'ok': True, 'suggestions': [_to_dict(s) for s in suggestions]})
    except Exception as exc:
        logger.error("list_suggestions 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.post('/suggestions/<suggestion_id>/apply')
def apply_suggestion(suggestion_id: str):
    try:
        ok = _get_adjuster().apply_suggestion(suggestion_id)
        if not ok:
            return jsonify({'error': '제안 적용 실패'}), 400
        return jsonify({'ok': True})
    except Exception as exc:
        logger.error("apply_suggestion 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.post('/suggestions/<suggestion_id>/reject')
def reject_suggestion(suggestion_id: str):
    data = request.get_json(force=True) or {}
    try:
        ok = _get_adjuster().reject_suggestion(suggestion_id, reason=data.get('reason'))
        if not ok:
            return jsonify({'error': '제안 없음'}), 404
        return jsonify({'ok': True})
    except Exception as exc:
        logger.error("reject_suggestion 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ══════════════════════════════════════════════════════════════════════════════
# 규칙
# ══════════════════════════════════════════════════════════════════════════════

@competitor_pricing_bp.get('/rules')
def list_rules():
    try:
        rules = _get_rules().get_rules()
        return jsonify({'ok': True, 'rules': [_to_dict(r) for r in rules]})
    except Exception as exc:
        logger.error("list_rules 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.post('/rules')
def add_rule():
    data = request.get_json(force=True) or {}
    try:
        rule = _get_rules().add_rule(data)
        return jsonify({'ok': True, 'rule': _to_dict(rule)}), 201
    except Exception as exc:
        logger.error("add_rule 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 400


@competitor_pricing_bp.delete('/rules/<rule_id>')
def remove_rule(rule_id: str):
    try:
        removed = _get_rules().remove_rule(rule_id)
        if not removed:
            return jsonify({'error': '규칙 없음'}), 404
        return jsonify({'ok': True})
    except Exception as exc:
        logger.error("remove_rule 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ══════════════════════════════════════════════════════════════════════════════
# 알림
# ══════════════════════════════════════════════════════════════════════════════

@competitor_pricing_bp.get('/alerts')
def list_alerts():
    severity_str = request.args.get('severity')
    alert_type_str = request.args.get('alert_type')
    acknowledged_str = request.args.get('acknowledged')
    try:
        from src.competitor_pricing.competitor_alerts import AlertSeverity, AlertType
        severity = AlertSeverity(severity_str) if severity_str else None
        alert_type = AlertType(alert_type_str) if alert_type_str else None
        acknowledged = (
            acknowledged_str.lower() == 'true' if acknowledged_str is not None else None
        )
        alerts = _get_alerts().get_alerts(
            severity=severity, alert_type=alert_type, acknowledged=acknowledged
        )
        return jsonify({'ok': True, 'alerts': [_to_dict(a) for a in alerts]})
    except Exception as exc:
        logger.error("list_alerts 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.get('/alerts/summary')
def alert_summary():
    try:
        summary = _get_alerts().get_alert_summary()
        return jsonify({'ok': True, 'summary': summary})
    except Exception as exc:
        logger.error("alert_summary 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.post('/alerts/<alert_id>/acknowledge')
def acknowledge_alert(alert_id: str):
    try:
        ok = _get_alerts().acknowledge_alert(alert_id)
        if not ok:
            return jsonify({'error': '알림 없음'}), 404
        return jsonify({'ok': True})
    except Exception as exc:
        logger.error("acknowledge_alert 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ══════════════════════════════════════════════════════════════════════════════
# 대시보드 / 스케줄
# ══════════════════════════════════════════════════════════════════════════════

@competitor_pricing_bp.get('/dashboard')
def dashboard():
    try:
        data = _get_dashboard().get_dashboard_data()
        return jsonify({'ok': True, 'dashboard': data})
    except Exception as exc:
        logger.error("dashboard 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@competitor_pricing_bp.get('/schedule')
def schedule():
    try:
        limit = min(int(request.args.get('limit', 10)), 100)
        entries = _get_scheduler().get_next_checks(limit=limit)
        stats = _get_scheduler().get_stats()
        return jsonify({
            'ok': True,
            'entries': [_to_dict(e) for e in entries],
            'stats': stats,
        })
    except Exception as exc:
        logger.error("schedule 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500
