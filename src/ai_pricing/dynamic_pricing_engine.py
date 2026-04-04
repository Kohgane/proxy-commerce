"""src/ai_pricing/dynamic_pricing_engine.py — AI 동적 가격 최적화 오케스트레이터 (Phase 97)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .competitor_tracker import CompetitorPriceTracker
from .demand_forecaster import DemandForecaster
from .price_alert_system import PriceAlertSystem
from .price_optimizer import OBJECTIVE_PROFIT, PriceOptimizer
from .pricing_analytics import PricingAnalytics
from .pricing_models import PricePoint, PricingDecision, PricingMetrics
from .pricing_rules import RuleContext, RuleResult, get_default_rules
from .pricing_scheduler import PricingScheduler

logger = logging.getLogger(__name__)

# 기본 전략 가중치
_DEFAULT_WEIGHTS = {
    'competitor_match': 0.35,
    'demand_surge': 0.25,
    'slow_mover': 0.20,
    'seasonal': 0.10,
    'bundle_pricing': 0.05,
    'margin_protection': 0.05,
}


class DynamicPricingEngine:
    """AI 기반 동적 가격 최적화 오케스트레이터.

    전략별 가중치 기반 앙상블 가격 결정.
    자동 모드: 즉시 반영, 수동 모드: 승인 대기.
    """

    def __init__(
        self,
        auto_mode: bool = False,
        objective: str = OBJECTIVE_PROFIT,
        min_margin_pct: float = 0.15,
        strategy_weights: Dict[str, float] = None,
    ) -> None:
        """
        Args:
            auto_mode: True이면 최적가 즉시 반영, False이면 승인 대기
            objective: 최적화 목적함수 (profit/revenue/market_share)
            min_margin_pct: 최소 마진율
            strategy_weights: 전략별 가중치 딕셔너리
        """
        self._auto_mode = auto_mode
        self._weights = strategy_weights or dict(_DEFAULT_WEIGHTS)

        self._rules = get_default_rules()
        self._competitor = CompetitorPriceTracker()
        self._forecaster = DemandForecaster()
        self._optimizer = PriceOptimizer(
            objective=objective,
            min_margin_pct=min_margin_pct,
        )
        self._alerts = PriceAlertSystem(min_margin_pct=min_margin_pct)
        self._analytics = PricingAnalytics()
        self._scheduler = PricingScheduler()

        # 가격 결정 이력: sku → list[PricingDecision]
        self._decisions: Dict[str, List[PricingDecision]] = {}
        # 현재 적용 가격 캐시: sku → float
        self._current_prices: Dict[str, float] = {}
        # 롤백 스택: sku → list[float]
        self._price_history: Dict[str, List[float]] = {}

    # ── 공개 API ──────────────────────────────────────────────────────────

    def optimize_sku(
        self,
        sku: str,
        base_price: float,
        cost: float = 0.0,
        stock_qty: int = 100,
        sales_velocity: float = 0.0,
        category: str = '',
        bundle_skus: List[str] = None,
        fx_rate_change: float = 0.0,
    ) -> PricingDecision:
        """단일 SKU의 최적 가격을 계산하고 결정을 반환한다.

        Args:
            sku: 상품 SKU
            base_price: 현재 판매가
            cost: 원가
            stock_qty: 재고 수량
            sales_velocity: 일 평균 판매량
            category: 상품 카테고리
            bundle_skus: 번들 구성 SKU 목록
            fx_rate_change: 환율 변동율 (%)

        Returns:
            PricingDecision
        """
        # 경쟁사 가격 수집
        competitors = self._competitor.collect_prices(sku, base_price)
        comp_prices = [
            cp.price * {'USD': 1340.0, 'JPY': 9.0, 'KRW': 1.0}.get(cp.currency, 1.0)
            for cp in competitors
        ]
        comp_min = min(comp_prices) if comp_prices else 0.0
        comp_avg = sum(comp_prices) / len(comp_prices) if comp_prices else 0.0

        # 수요 예측
        demand_forecast = self._forecaster.forecast(sku)
        demand_score = demand_forecast.seasonality_factor

        # 규칙 평가
        ctx = RuleContext(
            sku=sku,
            current_price=base_price,
            cost=cost,
            competitor_min=comp_min,
            competitor_avg=comp_avg,
            demand_score=demand_score,
            stock_qty=stock_qty,
            sales_velocity=sales_velocity,
            category=category,
            season_factor=demand_forecast.seasonality_factor,
            fx_rate_change=fx_rate_change,
            bundle_skus=bundle_skus or [],
        )
        rule_results = self._evaluate_rules(ctx)

        # 앙상블 가격 계산
        ensemble_price = self._ensemble_price(rule_results, base_price)

        # 최적화 적용
        pp = PricePoint(
            sku=sku,
            base_price=base_price,
            optimized_price=ensemble_price,
            margin=(ensemble_price - cost) / ensemble_price if ensemble_price > 0 and cost > 0 else 0.0,
            competitor_avg=comp_avg,
            demand_score=demand_score,
            cost=cost,
        )
        optimized = self._optimizer.optimize(pp)

        # 마진 위험 체크
        if cost > 0 and optimized.optimized_price > 0:
            margin = (optimized.optimized_price - cost) / optimized.optimized_price
            if margin < 0.15:
                self._alerts.alert_margin_risk(sku, optimized.optimized_price, cost, margin)

        # 가격 결정 생성
        strategy_names = ', '.join(r.rule_name for r in rule_results)
        decision = PricingDecision(
            sku=sku,
            old_price=base_price,
            new_price=optimized.optimized_price,
            reason='; '.join(r.reason for r in rule_results) or '앙상블 최적화',
            strategy=strategy_names or 'ensemble',
            approved=self._auto_mode,
        )

        if self._auto_mode:
            decision.apply()
            self._apply_price(sku, base_price, optimized.optimized_price)

        # 이력 기록
        if sku not in self._decisions:
            self._decisions[sku] = []
        self._decisions[sku].append(decision)
        self._analytics.record_decision(decision)

        # 경쟁사 알림 처리
        for alert in self._competitor.get_alerts(clear=True):
            self._alerts.alert_competitor_change(
                competitor_id=alert['competitor_id'],
                sku=alert['sku'],
                old_price=alert['prev_price'],
                new_price=alert['curr_price'],
                change_pct=alert['change_pct'],
            )

        logger.info(
            'SKU 최적화: %s | %s → %s | 전략: %s | 자동: %s',
            sku,
            base_price,
            optimized.optimized_price,
            strategy_names,
            self._auto_mode,
        )
        return decision

    def optimize_category(
        self,
        category: str,
        sku_price_map: Dict[str, Dict],
    ) -> List[PricingDecision]:
        """카테고리 내 모든 SKU를 일괄 최적화한다.

        Args:
            category: 카테고리명
            sku_price_map: {sku: {'price': float, 'cost': float, ...}} 매핑

        Returns:
            PricingDecision 목록
        """
        decisions = []
        for sku, info in sku_price_map.items():
            decision = self.optimize_sku(
                sku=sku,
                base_price=info.get('price', 0.0),
                cost=info.get('cost', 0.0),
                stock_qty=info.get('stock_qty', 100),
                sales_velocity=info.get('sales_velocity', 0.0),
                category=category,
                bundle_skus=info.get('bundle_skus'),
                fx_rate_change=info.get('fx_rate_change', 0.0),
            )
            decisions.append(decision)
        return decisions

    def approve_decision(self, decision_id: str) -> bool:
        """수동 모드에서 특정 가격 결정을 승인한다."""
        for sku_decisions in self._decisions.values():
            for d in sku_decisions:
                if d.decision_id == decision_id:
                    old = d.old_price
                    d.apply()
                    self._apply_price(d.sku, old, d.new_price)
                    return True
        return False

    def rollback_price(self, sku: str) -> Optional[float]:
        """SKU 가격을 이전 가격으로 롤백한다.

        Returns:
            롤백된 이전 가격 또는 None
        """
        history = self._price_history.get(sku, [])
        if len(history) < 2:
            return None
        # 마지막 가격 제거
        history.pop()
        prev_price = history[-1]
        self._current_prices[sku] = prev_price
        logger.info('가격 롤백: %s → %s', sku, prev_price)
        return prev_price

    def get_recommendations(self, limit: int = 20) -> List[Dict]:
        """AI 가격 추천 목록을 반환한다."""
        recommendations = []
        for sku, decisions in self._decisions.items():
            pending = [d for d in decisions if not d.approved]
            if pending:
                latest = pending[-1]
                recommendations.append({
                    'sku': sku,
                    'decision_id': latest.decision_id,
                    'current_price': latest.old_price,
                    'recommended_price': latest.new_price,
                    'change_pct': latest.price_change_pct,
                    'reason': latest.reason,
                    'strategy': latest.strategy,
                    'created_at': latest.created_at.isoformat(),
                })
        return recommendations[:limit]

    def get_metrics(self) -> PricingMetrics:
        """전체 메트릭을 반환한다."""
        return self._analytics.get_metrics()

    def get_history(self, sku: str) -> List[PricingDecision]:
        """SKU별 가격 결정 이력을 반환한다."""
        return list(self._decisions.get(sku, []))

    def set_mode(self, auto: bool) -> None:
        """자동/수동 모드를 전환한다."""
        self._auto_mode = auto
        logger.info('가격 모드 변경: %s', '자동' if auto else '수동')

    # ── 하위 서비스 접근자 ────────────────────────────────────────────────

    @property
    def competitor(self) -> CompetitorPriceTracker:
        return self._competitor

    @property
    def forecaster(self) -> DemandForecaster:
        return self._forecaster

    @property
    def optimizer(self) -> PriceOptimizer:
        return self._optimizer

    @property
    def analytics(self) -> PricingAnalytics:
        return self._analytics

    @property
    def scheduler(self) -> PricingScheduler:
        return self._scheduler

    @property
    def alerts(self) -> PriceAlertSystem:
        return self._alerts

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────

    def _evaluate_rules(self, ctx: RuleContext) -> List[RuleResult]:
        """모든 규칙을 평가하여 유효한 결과 목록을 반환한다."""
        results = []
        for rule in self._rules:
            try:
                result = rule.evaluate(ctx)
                if result is not None:
                    results.append(result)
            except Exception as exc:
                logger.warning('규칙 평가 오류 [%s]: %s', rule.name, exc)
        return results

    def _ensemble_price(
        self, rule_results: List[RuleResult], fallback: float
    ) -> float:
        """가중치 기반 앙상블 가격을 계산한다."""
        if not rule_results:
            return fallback

        # MarginProtectionRule은 최우선 (confidence=1.0)
        for r in rule_results:
            if r.rule_name == 'margin_protection' and r.confidence >= 1.0:
                return r.suggested_price

        total_weight = 0.0
        weighted_sum = 0.0
        for r in rule_results:
            w = self._weights.get(r.rule_name, 0.1) * r.confidence
            weighted_sum += r.suggested_price * w
            total_weight += w

        if total_weight == 0:
            return fallback
        return round(weighted_sum / total_weight, 2)

    def _apply_price(self, sku: str, old_price: float, new_price: float) -> None:
        """가격을 적용하고 이력에 기록한다."""
        if sku not in self._price_history:
            self._price_history[sku] = [old_price]
        self._price_history[sku].append(new_price)
        self._current_prices[sku] = new_price

        if old_price != new_price:
            self._alerts.alert_price_change(
                sku=sku,
                old_price=old_price,
                new_price=new_price,
                strategy='ensemble',
                auto_applied=self._auto_mode,
            )
