"""src/api/ai_pricing_api.py — AI 동적 가격 최적화 API Blueprint (Phase 97).

Blueprint: /api/v1/ai-pricing

엔드포인트:
  POST /optimize              — SKU/카테고리 가격 최적화 실행
  POST /simulate              — 가격 변경 시뮬레이션 (실제 반영 X)
  GET  /recommendations       — AI 가격 추천 목록
  GET  /competitors/<sku>     — 경쟁사 가격 비교
  GET  /forecast/<sku>        — 수요 예측 결과
  GET  /history/<sku>         — 가격 변경 이력
  GET  /analytics             — 가격 최적화 분석 리포트
  GET  /metrics               — 전체 메트릭 대시보드
  POST /rules                 — 가격 규칙 추가/수정
  GET  /rules                 — 가격 규칙 목록
  POST /schedule              — 가격 업데이트 스케줄 등록
  GET  /alerts                — 가격 알림 목록
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

ai_pricing_bp = Blueprint('ai_pricing', __name__, url_prefix='/api/v1/ai-pricing')

# 지연 초기화 엔진
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from ..ai_pricing.dynamic_pricing_engine import DynamicPricingEngine
        _engine = DynamicPricingEngine()
    return _engine


# ---------------------------------------------------------------------------
# POST /optimize
# ---------------------------------------------------------------------------

@ai_pricing_bp.post('/optimize')
def optimize():
    """POST /api/v1/ai-pricing/optimize — SKU/카테고리 가격 최적화 실행."""
    body = request.get_json(silent=True) or {}
    sku = body.get('sku')
    category = body.get('category')

    engine = _get_engine()

    try:
        if sku:
            decision = engine.optimize_sku(
                sku=sku,
                base_price=float(body.get('base_price', 0)),
                cost=float(body.get('cost', 0)),
                stock_qty=int(body.get('stock_qty', 100)),
                sales_velocity=float(body.get('sales_velocity', 0)),
                category=body.get('category', ''),
                bundle_skus=body.get('bundle_skus'),
                fx_rate_change=float(body.get('fx_rate_change', 0)),
            )
            return jsonify({
                'decision_id': decision.decision_id,
                'sku': decision.sku,
                'old_price': decision.old_price,
                'new_price': decision.new_price,
                'change_pct': decision.price_change_pct,
                'reason': decision.reason,
                'strategy': decision.strategy,
                'approved': decision.approved,
                'applied_at': decision.applied_at.isoformat() if decision.applied_at else None,
            })

        if category:
            sku_map = body.get('sku_map', {})
            decisions = engine.optimize_category(category, sku_map)
            return jsonify({
                'category': category,
                'optimized': len(decisions),
                'decisions': [
                    {
                        'sku': d.sku,
                        'old_price': d.old_price,
                        'new_price': d.new_price,
                        'change_pct': d.price_change_pct,
                        'approved': d.approved,
                    }
                    for d in decisions
                ],
            })

        return jsonify({'error': 'sku 또는 category 파라미터 필요'}), 400

    except Exception as exc:
        logger.error('가격 최적화 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /simulate
# ---------------------------------------------------------------------------

@ai_pricing_bp.post('/simulate')
def simulate():
    """POST /api/v1/ai-pricing/simulate — 가격 변경 시뮬레이션."""
    body = request.get_json(silent=True) or {}
    sku = body.get('sku', '')
    base_price = float(body.get('base_price', 0))
    test_price = float(body.get('test_price', 0))
    cost = float(body.get('cost', 0))
    elasticity = float(body.get('elasticity', -1.0))
    base_qty = float(body.get('base_qty', 100))

    if not sku or base_price <= 0 or test_price <= 0:
        return jsonify({'error': 'sku, base_price, test_price 필수'}), 400

    try:
        from ..ai_pricing.pricing_models import PricePoint
        engine = _get_engine()
        pp = PricePoint(sku=sku, base_price=base_price, cost=cost)
        result = engine.optimizer.simulate(pp, test_price, elasticity, base_qty)
        result['sku'] = sku
        return jsonify(result)
    except Exception as exc:
        logger.error('시뮬레이션 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /recommendations
# ---------------------------------------------------------------------------

@ai_pricing_bp.get('/recommendations')
def recommendations():
    """GET /api/v1/ai-pricing/recommendations — AI 가격 추천 목록."""
    limit = int(request.args.get('limit', 20))
    try:
        engine = _get_engine()
        recs = engine.get_recommendations(limit=limit)
        return jsonify({'recommendations': recs, 'count': len(recs)})
    except Exception as exc:
        logger.error('추천 조회 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /competitors/<sku>
# ---------------------------------------------------------------------------

@ai_pricing_bp.get('/competitors/<sku>')
def competitor_prices(sku: str):
    """GET /api/v1/ai-pricing/competitors/<sku> — 경쟁사 가격 비교."""
    our_price = float(request.args.get('our_price', 0))
    try:
        engine = _get_engine()
        positioning = engine.competitor.get_positioning(sku)
        gap = engine.competitor.get_price_gap(sku, our_price) if our_price > 0 else {}
        latest = {
            cid: {
                'price': cp.price,
                'currency': cp.currency,
                'observed_at': cp.observed_at.isoformat(),
            }
            for cid, cp in engine.competitor.get_latest(sku).items()
        }
        return jsonify({
            'sku': sku,
            'positioning': positioning,
            'price_gap': gap,
            'latest_prices': latest,
        })
    except Exception as exc:
        logger.error('경쟁사 가격 조회 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /forecast/<sku>
# ---------------------------------------------------------------------------

@ai_pricing_bp.get('/forecast/<sku>')
def demand_forecast(sku: str):
    """GET /api/v1/ai-pricing/forecast/<sku> — 수요 예측 결과."""
    try:
        engine = _get_engine()
        forecast = engine.forecaster.forecast(sku)
        elasticity = engine.forecaster.calculate_elasticity(sku)
        return jsonify({
            'sku': forecast.sku,
            'period': forecast.period,
            'predicted_qty': forecast.predicted_qty,
            'confidence_interval': list(forecast.confidence_interval),
            'seasonality_factor': forecast.seasonality_factor,
            'forecast_method': forecast.forecast_method,
            'elasticity': elasticity,
            'monthly_seasonality': engine.forecaster.get_monthly_seasonality(),
        })
    except Exception as exc:
        logger.error('수요 예측 조회 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /history/<sku>
# ---------------------------------------------------------------------------

@ai_pricing_bp.get('/history/<sku>')
def price_history(sku: str):
    """GET /api/v1/ai-pricing/history/<sku> — 가격 변경 이력."""
    try:
        engine = _get_engine()
        history = engine.get_history(sku)
        return jsonify({
            'sku': sku,
            'count': len(history),
            'history': [
                {
                    'decision_id': d.decision_id,
                    'old_price': d.old_price,
                    'new_price': d.new_price,
                    'change_pct': d.price_change_pct,
                    'reason': d.reason,
                    'strategy': d.strategy,
                    'approved': d.approved,
                    'applied_at': d.applied_at.isoformat() if d.applied_at else None,
                    'created_at': d.created_at.isoformat(),
                }
                for d in history
            ],
        })
    except Exception as exc:
        logger.error('가격 이력 조회 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /analytics
# ---------------------------------------------------------------------------

@ai_pricing_bp.get('/analytics')
def analytics():
    """GET /api/v1/ai-pricing/analytics — 가격 최적화 분석 리포트."""
    try:
        engine = _get_engine()
        effects = engine.analytics.analyze_all_effects()
        roi = engine.analytics.roi_analysis()
        return jsonify({
            'effects': effects,
            'roi': roi,
        })
    except Exception as exc:
        logger.error('분석 리포트 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------

@ai_pricing_bp.get('/metrics')
def metrics():
    """GET /api/v1/ai-pricing/metrics — 전체 메트릭 대시보드."""
    try:
        engine = _get_engine()
        m = engine.get_metrics()
        return jsonify({
            'total_optimized': m.total_optimized,
            'avg_price_change_pct': m.avg_price_change_pct,
            'revenue_impact': m.revenue_impact,
            'margin_impact': m.margin_impact,
            'skus_increased': m.skus_increased,
            'skus_decreased': m.skus_decreased,
            'skus_unchanged': m.skus_unchanged,
            'pending_approvals': m.pending_approvals,
            'last_run_at': m.last_run_at.isoformat() if m.last_run_at else None,
        })
    except Exception as exc:
        logger.error('메트릭 조회 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /rules
# ---------------------------------------------------------------------------

@ai_pricing_bp.post('/rules')
def add_rule():
    """POST /api/v1/ai-pricing/rules — 가격 규칙 추가/수정."""
    body = request.get_json(silent=True) or {}
    rule_type = body.get('rule_type', '')

    try:
        from ..ai_pricing import pricing_rules as pr
        engine = _get_engine()

        rule_map = {
            'competitor_match': lambda: pr.CompetitorMatchRule(
                undercut_pct=body.get('undercut_pct', 0.02),
                undercut_abs=body.get('undercut_abs', 0.0),
            ),
            'demand_surge': lambda: pr.DemandSurgeRule(
                surge_threshold=body.get('surge_threshold', 1.5),
                surge_pct=body.get('surge_pct', 0.10),
            ),
            'slow_mover': lambda: pr.SlowMoverRule(
                slow_threshold_days=body.get('slow_threshold_days', 30.0),
                discount_pct=body.get('discount_pct', 0.10),
            ),
            'seasonal': lambda: pr.SeasonalRule(
                peak_boost=body.get('peak_boost', 0.08),
                off_discount=body.get('off_discount', 0.05),
            ),
            'bundle_pricing': lambda: pr.BundlePricingRule(
                bundle_discount_pct=body.get('bundle_discount_pct', 0.05),
            ),
            'margin_protection': lambda: pr.MarginProtectionRule(
                min_margin_pct=body.get('min_margin_pct', 0.15),
            ),
        }

        if rule_type not in rule_map:
            return jsonify({'error': f'알 수 없는 규칙 유형: {rule_type}'}), 400

        new_rule = rule_map[rule_type]()
        # 기존 같은 이름 규칙 교체
        engine._rules = [r for r in engine._rules if r.name != new_rule.name]
        engine._rules.append(new_rule)

        return jsonify({'status': 'ok', 'rule_type': rule_type, 'message': '규칙 추가/수정 완료'})

    except Exception as exc:
        logger.error('규칙 추가 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /rules
# ---------------------------------------------------------------------------

@ai_pricing_bp.get('/rules')
def list_rules():
    """GET /api/v1/ai-pricing/rules — 가격 규칙 목록."""
    try:
        engine = _get_engine()
        rules = [
            {'name': r.name, 'class': type(r).__name__}
            for r in engine._rules
        ]
        return jsonify({'rules': rules, 'count': len(rules)})
    except Exception as exc:
        logger.error('규칙 목록 조회 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /schedule
# ---------------------------------------------------------------------------

@ai_pricing_bp.post('/schedule')
def add_schedule():
    """POST /api/v1/ai-pricing/schedule — 가격 업데이트 스케줄 등록."""
    body = request.get_json(silent=True) or {}
    schedule_type = body.get('schedule_type', 'daily')
    skus = body.get('skus', [])
    category = body.get('category', '')
    hour = body.get('hour')

    try:
        engine = _get_engine()
        job = engine.scheduler.add_schedule(
            schedule_type=schedule_type,
            skus=skus,
            category=category,
            hour=hour,
        )
        return jsonify(job.to_dict()), 201
    except Exception as exc:
        logger.error('스케줄 등록 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /alerts
# ---------------------------------------------------------------------------

@ai_pricing_bp.get('/alerts')
def get_alerts():
    """GET /api/v1/ai-pricing/alerts — 가격 알림 목록."""
    alert_type = request.args.get('type')
    limit = int(request.args.get('limit', 50))
    try:
        engine = _get_engine()
        alerts = engine.alerts.get_alerts(alert_type=alert_type, limit=limit)
        return jsonify({'alerts': alerts, 'count': len(alerts)})
    except Exception as exc:
        logger.error('알림 조회 오류: %s', exc)
        return jsonify({'error': str(exc)}), 500
