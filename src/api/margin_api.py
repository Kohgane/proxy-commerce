"""src/api/margin_api.py — 실시간 마진 계산기 API Blueprint (Phase 110).

Blueprint: /api/v1/margin

엔드포인트:
  GET    /api/v1/margin/<product_id>                   # 상품 마진 계산
  GET    /api/v1/margin/<product_id>/breakdown          # 비용 상세 분해
  POST   /api/v1/margin/bulk                           # 일괄 마진 계산
  POST   /api/v1/margin/recalculate                    # 전체 재계산
  GET    /api/v1/margin/alerts                         # 알림 목록
  GET    /api/v1/margin/alerts/summary                 # 알림 요약
  POST   /api/v1/margin/alerts/<alert_id>/acknowledge  # 알림 확인
  POST   /api/v1/margin/simulate/price                 # 가격 변경 시뮬레이션
  POST   /api/v1/margin/simulate/exchange-rate         # 환율 변동 시뮬레이션
  POST   /api/v1/margin/simulate/cost                  # 비용 변경 시뮬레이션
  POST   /api/v1/margin/simulate/break-even            # 손익분기 계산
  POST   /api/v1/margin/simulate/target-price          # 목표 마진 판매가 계산
  POST   /api/v1/margin/simulate/what-if               # 시나리오 비교 분석
  GET    /api/v1/margin/ranking                        # 수익성 순위
  GET    /api/v1/margin/loss-products                  # 적자 상품 목록
  GET    /api/v1/margin/low-margin                     # 저마진 상품 목록
  GET    /api/v1/margin/distribution                   # 마진율 분포
  GET    /api/v1/margin/channel-profitability           # 채널별 수익성
  GET    /api/v1/margin/trend/<product_id>             # 상품 마진 추이
  GET    /api/v1/margin/trend/overall                  # 전체 마진 추이
  GET    /api/v1/margin/trend/channel/<channel>        # 채널별 마진 추이
  GET    /api/v1/margin/trend/declining                # 마진 하락 상품
  GET    /api/v1/margin/config                         # 설정 조회
  PUT    /api/v1/margin/config                         # 설정 업데이트
  GET    /api/v1/margin/platform-fees                  # 플랫폼 수수료 조회
  GET    /api/v1/margin/platform-fees/<channel>        # 채널별 수수료 구조
  GET    /api/v1/margin/dashboard                      # 마진 대시보드 데이터
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

margin_bp = Blueprint(
    'margin',
    __name__,
    url_prefix='/api/v1/margin',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_calculator = None
_breakdown_svc = None
_alert_svc = None
_simulator = None
_profitability = None
_trend = None
_config = None
_fee_calc = None


def _get_calculator():
    global _calculator
    if _calculator is None:
        from src.margin_calculator.calculator import RealTimeMarginCalculator
        _calculator = RealTimeMarginCalculator()
    return _calculator


def _get_breakdown():
    global _breakdown_svc
    if _breakdown_svc is None:
        from src.margin_calculator.cost_breakdown import CostBreakdownService
        _breakdown_svc = CostBreakdownService(_get_calculator())
    return _breakdown_svc


def _get_alert_svc():
    global _alert_svc
    if _alert_svc is None:
        from src.margin_calculator.margin_alerts import MarginAlertService
        _alert_svc = MarginAlertService(_get_calculator(), _get_config())
    return _alert_svc


def _get_simulator():
    global _simulator
    if _simulator is None:
        from src.margin_calculator.margin_simulator import MarginSimulator
        _simulator = MarginSimulator(_get_calculator())
    return _simulator


def _get_profitability():
    global _profitability
    if _profitability is None:
        from src.margin_calculator.profitability import ProfitabilityAnalyzer
        _profitability = ProfitabilityAnalyzer(_get_calculator())
    return _profitability


def _get_trend():
    global _trend
    if _trend is None:
        from src.margin_calculator.margin_trend import MarginTrendAnalyzer
        _trend = MarginTrendAnalyzer(_get_calculator())
    return _trend


def _get_config():
    global _config
    if _config is None:
        from src.margin_calculator.margin_config import MarginConfig
        _config = MarginConfig()
    return _config


def _get_fee_calc():
    global _fee_calc
    if _fee_calc is None:
        from src.margin_calculator.platform_fees import PlatformFeeCalculator
        _fee_calc = PlatformFeeCalculator()
    return _fee_calc


# ── 마진 계산 ─────────────────────────────────────────────────────────────────

@margin_bp.get('/<product_id>')
def get_margin(product_id: str):
    """상품 마진 계산."""
    channel = request.args.get('channel', 'internal')
    try:
        result = _get_calculator().calculate_margin(product_id, channel)
        return jsonify({'success': True, 'margin': result.to_dict()})
    except Exception as exc:
        logger.error("get_margin 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.get('/<product_id>/breakdown')
def get_breakdown(product_id: str):
    """비용 상세 분해."""
    channel = request.args.get('channel', 'internal')
    try:
        breakdown = _get_breakdown().get_cost_breakdown(product_id, channel)
        return jsonify({'success': True, 'breakdown': breakdown})
    except Exception as exc:
        logger.error("get_breakdown 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.post('/bulk')
def bulk_margin():
    """일괄 마진 계산."""
    data = request.get_json(force=True) or {}
    product_ids = data.get('product_ids')
    channel = data.get('channel', 'internal')
    try:
        results = _get_calculator().calculate_bulk_margins(product_ids, channel)
        return jsonify({
            'success': True,
            'results': [r.to_dict() for r in results],
            'total': len(results),
        })
    except Exception as exc:
        logger.error("bulk_margin 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.post('/recalculate')
def recalculate():
    """전체 재계산."""
    data = request.get_json(force=True) or {}
    channel = data.get('channel')
    try:
        result = _get_calculator().recalculate_all(channel=channel)
        return jsonify({'success': True, **result})
    except Exception as exc:
        logger.error("recalculate 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ── 알림 ──────────────────────────────────────────────────────────────────────

@margin_bp.get('/alerts')
def get_alerts():
    """알림 목록."""
    severity = request.args.get('severity')
    channel = request.args.get('channel')
    ack_str = request.args.get('acknowledged')
    acknowledged = None if ack_str is None else ack_str.lower() == 'true'
    try:
        alerts = _get_alert_svc().get_alerts(
            severity=severity, channel=channel, acknowledged=acknowledged
        )
        return jsonify({
            'success': True,
            'alerts': [a.to_dict() for a in alerts],
            'total': len(alerts),
        })
    except Exception as exc:
        logger.error("get_alerts 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.get('/alerts/summary')
def get_alert_summary():
    """알림 요약."""
    try:
        summary = _get_alert_svc().get_alert_summary()
        return jsonify({'success': True, 'summary': summary})
    except Exception as exc:
        logger.error("get_alert_summary 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.post('/alerts/<alert_id>/acknowledge')
def acknowledge_alert(alert_id: str):
    """알림 확인."""
    try:
        alert = _get_alert_svc().acknowledge_alert(alert_id)
        if not alert:
            return jsonify({'error': 'alert not found'}), 404
        return jsonify({'success': True, 'alert': alert.to_dict()})
    except Exception as exc:
        logger.error("acknowledge_alert 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ── 시뮬레이션 ────────────────────────────────────────────────────────────────

@margin_bp.post('/simulate/price')
def simulate_price():
    """가격 변경 시뮬레이션."""
    data = request.get_json(force=True) or {}
    product_id = data.get('product_id', '')
    new_price = float(data.get('new_price', 0))
    channel = data.get('channel', 'internal')
    if not product_id:
        return jsonify({'error': 'product_id 필요'}), 400
    try:
        result = _get_simulator().simulate_price_change(product_id, new_price, channel)
        return jsonify({'success': True, 'simulation': result})
    except Exception as exc:
        logger.error("simulate_price 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.post('/simulate/exchange-rate')
def simulate_exchange_rate():
    """환율 변동 시뮬레이션."""
    data = request.get_json(force=True) or {}
    product_id = data.get('product_id', '')
    new_rate = float(data.get('new_rate', 1.0))
    channel = data.get('channel', 'internal')
    if not product_id:
        return jsonify({'error': 'product_id 필요'}), 400
    try:
        result = _get_simulator().simulate_exchange_rate(product_id, new_rate, channel)
        return jsonify({'success': True, 'simulation': result})
    except Exception as exc:
        logger.error("simulate_exchange_rate 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.post('/simulate/cost')
def simulate_cost():
    """비용 변경 시뮬레이션."""
    data = request.get_json(force=True) or {}
    product_id = data.get('product_id', '')
    cost_type = data.get('cost_type', '')
    new_value = float(data.get('new_value', 0))
    channel = data.get('channel', 'internal')
    if not product_id or not cost_type:
        return jsonify({'error': 'product_id, cost_type 필요'}), 400
    try:
        result = _get_simulator().simulate_cost_change(product_id, cost_type, new_value, channel)
        return jsonify({'success': True, 'simulation': result})
    except Exception as exc:
        logger.error("simulate_cost 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.post('/simulate/break-even')
def simulate_break_even():
    """손익분기 계산."""
    data = request.get_json(force=True) or {}
    product_id = data.get('product_id', '')
    channel = data.get('channel', 'internal')
    if not product_id:
        return jsonify({'error': 'product_id 필요'}), 400
    try:
        result = _get_simulator().find_break_even_price(product_id, channel)
        return jsonify({'success': True, 'result': result})
    except Exception as exc:
        logger.error("simulate_break_even 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.post('/simulate/target-price')
def simulate_target_price():
    """목표 마진 판매가 계산."""
    data = request.get_json(force=True) or {}
    product_id = data.get('product_id', '')
    target_margin = float(data.get('target_margin', 15.0))
    channel = data.get('channel', 'internal')
    if not product_id:
        return jsonify({'error': 'product_id 필요'}), 400
    try:
        result = _get_simulator().find_target_margin_price(product_id, target_margin, channel)
        return jsonify({'success': True, 'result': result})
    except Exception as exc:
        logger.error("simulate_target_price 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.post('/simulate/what-if')
def simulate_what_if():
    """시나리오 비교 분석."""
    data = request.get_json(force=True) or {}
    product_id = data.get('product_id', '')
    scenarios = data.get('scenarios', [])
    channel = data.get('channel', 'internal')
    if not product_id:
        return jsonify({'error': 'product_id 필요'}), 400
    try:
        result = _get_simulator().what_if_analysis(product_id, scenarios, channel)
        return jsonify({'success': True, 'analysis': result})
    except Exception as exc:
        logger.error("simulate_what_if 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ── 수익성 ────────────────────────────────────────────────────────────────────

@margin_bp.get('/ranking')
def get_ranking():
    """수익성 순위."""
    channel = request.args.get('channel', 'internal')
    limit = int(request.args.get('limit', 20))
    sort_by = request.args.get('sort_by', 'margin_rate')
    reverse = request.args.get('order', 'desc').lower() != 'asc'
    try:
        ranking = _get_profitability().get_profitability_ranking(
            limit=limit, channel=channel, sort_by=sort_by, reverse=reverse
        )
        return jsonify({'success': True, 'ranking': ranking, 'total': len(ranking)})
    except Exception as exc:
        logger.error("get_ranking 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.get('/loss-products')
def get_loss_products():
    """적자 상품 목록."""
    channel = request.args.get('channel', 'internal')
    try:
        products = _get_profitability().get_loss_products(channel)
        return jsonify({'success': True, 'products': products, 'total': len(products)})
    except Exception as exc:
        logger.error("get_loss_products 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.get('/low-margin')
def get_low_margin():
    """저마진 상품 목록."""
    channel = request.args.get('channel', 'internal')
    threshold = float(request.args.get('threshold', 5.0))
    try:
        products = _get_profitability().get_low_margin_products(threshold, channel)
        return jsonify({'success': True, 'products': products, 'total': len(products)})
    except Exception as exc:
        logger.error("get_low_margin 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.get('/distribution')
def get_distribution():
    """마진율 분포."""
    channel = request.args.get('channel', 'internal')
    try:
        dist = _get_profitability().get_profitability_distribution(channel)
        return jsonify({'success': True, **dist})
    except Exception as exc:
        logger.error("get_distribution 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.get('/channel-profitability')
def get_channel_profitability():
    """채널별 수익성."""
    try:
        result = _get_profitability().get_channel_profitability()
        return jsonify({'success': True, 'channels': result})
    except Exception as exc:
        logger.error("get_channel_profitability 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ── 추이 ──────────────────────────────────────────────────────────────────────

@margin_bp.get('/trend/<product_id>')
def get_product_trend(product_id: str):
    """상품 마진 추이."""
    period = request.args.get('period', 'monthly')
    interval = request.args.get('interval', 'day')
    try:
        trend = _get_trend().get_product_trend(product_id, period, interval)
        return jsonify({'success': True, 'trend': trend})
    except Exception as exc:
        logger.error("get_product_trend 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.get('/trend/overall')
def get_overall_trend():
    """전체 마진 추이."""
    period = request.args.get('period', 'monthly')
    interval = request.args.get('interval', 'day')
    channel = request.args.get('channel', 'internal')
    try:
        trend = _get_trend().get_overall_trend(period, interval, channel=channel)
        return jsonify({'success': True, 'trend': trend})
    except Exception as exc:
        logger.error("get_overall_trend 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.get('/trend/channel/<channel>')
def get_channel_trend(channel: str):
    """채널별 마진 추이."""
    period = request.args.get('period', 'monthly')
    interval = request.args.get('interval', 'day')
    try:
        trend = _get_trend().get_channel_trend(channel, period, interval)
        return jsonify({'success': True, 'trend': trend})
    except Exception as exc:
        logger.error("get_channel_trend 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.get('/trend/declining')
def get_declining():
    """마진 하락 상품."""
    threshold = float(request.args.get('threshold', 2.0))
    try:
        declining = _get_trend().detect_margin_decline(threshold)
        return jsonify({'success': True, 'declining': declining, 'total': len(declining)})
    except Exception as exc:
        logger.error("get_declining 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ── 설정 ──────────────────────────────────────────────────────────────────────

@margin_bp.get('/config')
def get_config():
    """설정 조회."""
    product_id = request.args.get('product_id')
    category = request.args.get('category')
    try:
        cfg = _get_config().get_config(product_id=product_id, category=category)
        return jsonify({'success': True, 'config': cfg})
    except Exception as exc:
        logger.error("get_config 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.put('/config')
def update_config():
    """설정 업데이트."""
    data = request.get_json(force=True) or {}
    try:
        updated = _get_config().update_config(data)
        return jsonify({'success': True, 'config': updated})
    except Exception as exc:
        logger.error("update_config 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ── 플랫폼 수수료 ─────────────────────────────────────────────────────────────

@margin_bp.get('/platform-fees')
def get_all_platform_fees():
    """전체 플랫폼 수수료 조회."""
    try:
        fees = _get_fee_calc().get_all_fee_structures()
        return jsonify({'success': True, 'fees': fees})
    except Exception as exc:
        logger.error("get_all_platform_fees 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


@margin_bp.get('/platform-fees/<channel>')
def get_channel_fees(channel: str):
    """채널별 수수료 구조."""
    try:
        fee_structure = _get_fee_calc().get_fee_structure(channel)
        return jsonify({'success': True, 'fee_structure': fee_structure})
    except Exception as exc:
        logger.error("get_channel_fees 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500


# ── 대시보드 ──────────────────────────────────────────────────────────────────

@margin_bp.get('/dashboard')
def get_dashboard():
    """마진 대시보드 데이터."""
    channel = request.args.get('channel', 'internal')
    try:
        profitability = _get_profitability()
        alert_svc = _get_alert_svc()
        trend = _get_trend()

        distribution = profitability.get_profitability_distribution(channel)
        loss_products = profitability.get_loss_products(channel)
        low_margin = profitability.get_low_margin_products(5.0, channel)
        alert_summary = alert_svc.get_alert_summary()
        trend_summary = trend.get_trend_summary()
        channel_profitability = profitability.get_channel_profitability()

        return jsonify({
            'success': True,
            'channel': channel,
            'distribution': distribution,
            'loss_count': len(loss_products),
            'low_margin_count': len(low_margin),
            'alert_summary': alert_summary,
            'trend_summary': trend_summary,
            'channel_profitability': channel_profitability,
        })
    except Exception as exc:
        logger.error("get_dashboard 오류: %s", exc)
        return jsonify({'error': '요청 처리 중 오류가 발생했습니다.'}), 500
