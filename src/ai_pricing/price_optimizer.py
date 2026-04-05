"""src/ai_pricing/price_optimizer.py — 가격 최적화 엔진 (Phase 97)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .pricing_models import PricePoint
from .pricing_rules import get_default_rules

logger = logging.getLogger(__name__)

# 최적화 목적함수
OBJECTIVE_REVENUE = 'revenue'
OBJECTIVE_PROFIT = 'profit'
OBJECTIVE_MARKET_SHARE = 'market_share'


class PriceOptimizer:
    """목적함수 기반 가격 최적화 엔진.

    매출 최대화, 이익 최대화, 시장점유율 최대화 중 선택하여
    가격 탄력성 기반 최적 가격을 계산한다.
    """

    def __init__(
        self,
        objective: str = OBJECTIVE_PROFIT,
        min_margin_pct: float = 0.15,
        min_price_floor: float = 0.0,
        max_price_ceiling: float = float('inf'),
        competitor_bound_pct: float = 0.20,
    ) -> None:
        """
        Args:
            objective: 최적화 목적 (revenue/profit/market_share)
            min_margin_pct: 최소 마진율 제약
            min_price_floor: 최저 가격 제약 (KRW)
            max_price_ceiling: 최고 가격 제약 (KRW)
            competitor_bound_pct: 경쟁사 평균 대비 최대 허용 ±%
        """
        self._objective = objective
        self._min_margin = min_margin_pct
        self._min_floor = min_price_floor
        self._max_ceiling = max_price_ceiling
        self._comp_bound = competitor_bound_pct
        self._rules = get_default_rules()
        # A/B 테스트 실험 저장
        self._ab_experiments: Dict[str, Dict] = {}

    # ── 메인 최적화 ───────────────────────────────────────────────────────

    def optimize(self, price_point: PricePoint, elasticity: float = -1.0) -> PricePoint:
        """최적 가격을 계산하여 price_point를 업데이트한다.

        Args:
            price_point: 현재 가격 정보
            elasticity: 가격 탄력성 (음수 = 정상재)

        Returns:
            최적가가 반영된 PricePoint
        """
        candidate = self._compute_candidate(price_point, elasticity)
        candidate = self._apply_constraints(candidate, price_point)
        price_point.optimized_price = candidate
        price_point.confidence = self._compute_confidence(price_point)
        return price_point

    def _compute_candidate(self, pp: PricePoint, elasticity: float) -> float:
        """목적함수별 후보 가격을 계산한다."""
        if self._objective == OBJECTIVE_REVENUE:
            return self._revenue_optimal(pp, elasticity)
        if self._objective == OBJECTIVE_MARKET_SHARE:
            return self._market_share_optimal(pp)
        # 기본: PROFIT
        return self._profit_optimal(pp, elasticity)

    def _revenue_optimal(self, pp: PricePoint, elasticity: float) -> float:
        """탄력성 기반 매출 최대화 가격 (Lerner 공식)."""
        if elasticity >= 0 or pp.base_price <= 0:
            return pp.base_price
        # 최적 마크업 = 1 / |e| → 최적 가격 = cost / (1 - 1/|e|)
        e = abs(elasticity)
        if e <= 1:
            # 비탄력적 — 가격 인상
            return round(pp.base_price * 1.05, 2)
        optimal = pp.cost / (1 - 1 / e) if pp.cost > 0 else pp.base_price * 0.95
        return round(optimal, 2)

    def _profit_optimal(self, pp: PricePoint, elasticity: float) -> float:
        """이익 최대화 가격."""
        if pp.cost <= 0:
            return pp.base_price
        e = abs(elasticity) if elasticity < 0 else 1.0
        if e <= 1:
            markup = 1 + self._min_margin + 0.05
        else:
            markup = max(1 + self._min_margin, 1 / (1 - 1 / e))
        return round(pp.cost * markup, 2)

    def _market_share_optimal(self, pp: PricePoint) -> float:
        """시장점유율 최대화 — 경쟁사 평균보다 낮게 설정."""
        if pp.competitor_avg <= 0:
            return round(pp.base_price * 0.97, 2)
        return round(pp.competitor_avg * 0.97, 2)

    def _apply_constraints(self, candidate: float, pp: PricePoint) -> float:
        """제약 조건을 적용하여 최종 가격을 결정한다."""
        # 1. 최소 마진 보호
        if pp.cost > 0:
            min_by_margin = pp.cost / (1 - self._min_margin)
            candidate = max(candidate, min_by_margin)

        # 2. 최저/최고 가격 범위
        if self._min_floor > 0:
            candidate = max(candidate, self._min_floor)
        if self._max_ceiling < float('inf'):
            candidate = min(candidate, self._max_ceiling)

        # 3. 경쟁사 대비 ±N% 범위
        if pp.competitor_avg > 0 and self._comp_bound > 0:
            lower = pp.competitor_avg * (1 - self._comp_bound)
            upper = pp.competitor_avg * (1 + self._comp_bound)
            candidate = max(candidate, lower)
            candidate = min(candidate, upper)

        return round(candidate, 2)

    def _compute_confidence(self, pp: PricePoint) -> float:
        """신뢰도를 계산한다 (0.0~1.0)."""
        score = 0.5
        if pp.competitor_avg > 0:
            score += 0.2
        if pp.demand_score != 1.0:
            score += 0.15
        if pp.cost > 0:
            score += 0.15
        return round(min(score, 1.0), 4)

    # ── 시뮬레이션 ────────────────────────────────────────────────────────

    def simulate(
        self,
        price_point: PricePoint,
        test_price: float,
        elasticity: float = -1.0,
        base_qty: float = 100.0,
    ) -> Dict:
        """가격 변경 시 예상 매출/이익을 시뮬레이션한다.

        Args:
            price_point: 현재 가격 정보
            test_price: 테스트 가격
            elasticity: 가격 탄력성
            base_qty: 현재 판매량 기준

        Returns:
            current/new 각각 qty/revenue/profit 비교
        """
        cur_price = price_point.base_price
        cost = price_point.cost

        # 가격 변동에 따른 수요 변화
        if cur_price > 0 and elasticity < 0:
            price_change_pct = (test_price - cur_price) / cur_price
            qty_change_pct = elasticity * price_change_pct
            new_qty = base_qty * (1 + qty_change_pct)
        else:
            new_qty = base_qty

        new_qty = max(0, new_qty)

        cur_revenue = cur_price * base_qty
        new_revenue = test_price * new_qty
        cur_profit = (cur_price - cost) * base_qty if cost > 0 else cur_revenue * 0.15
        new_profit = (test_price - cost) * new_qty if cost > 0 else new_revenue * 0.15

        return {
            'current': {
                'price': cur_price,
                'qty': round(base_qty, 2),
                'revenue': round(cur_revenue, 2),
                'profit': round(cur_profit, 2),
            },
            'new': {
                'price': test_price,
                'qty': round(new_qty, 2),
                'revenue': round(new_revenue, 2),
                'profit': round(new_profit, 2),
            },
            'delta': {
                'revenue': round(new_revenue - cur_revenue, 2),
                'profit': round(new_profit - cur_profit, 2),
                'revenue_pct': round((new_revenue - cur_revenue) / cur_revenue * 100, 2)
                if cur_revenue > 0 else 0.0,
            },
        }

    # ── A/B 테스트 연동 ───────────────────────────────────────────────────

    def create_ab_experiment(
        self,
        experiment_id: str,
        sku: str,
        control_price: float,
        variant_price: float,
    ) -> Dict:
        """A/B 가격 실험을 등록한다."""
        exp = {
            'experiment_id': experiment_id,
            'sku': sku,
            'control_price': control_price,
            'variant_price': variant_price,
            'control_impressions': 0,
            'variant_impressions': 0,
            'control_conversions': 0,
            'variant_conversions': 0,
            'status': 'running',
        }
        self._ab_experiments[experiment_id] = exp
        return exp

    def record_ab_result(
        self,
        experiment_id: str,
        variant: str,
        converted: bool,
    ) -> bool:
        """A/B 실험 결과를 기록한다."""
        exp = self._ab_experiments.get(experiment_id)
        if not exp:
            return False
        if variant == 'control':
            exp['control_impressions'] += 1
            if converted:
                exp['control_conversions'] += 1
        else:
            exp['variant_impressions'] += 1
            if converted:
                exp['variant_conversions'] += 1
        return True

    def get_ab_result(self, experiment_id: str) -> Optional[Dict]:
        """A/B 실험 결과를 반환한다."""
        exp = self._ab_experiments.get(experiment_id)
        if not exp:
            return None
        ci = exp['control_impressions']
        vi = exp['variant_impressions']
        ctrl_cvr = exp['control_conversions'] / ci if ci > 0 else 0.0
        var_cvr = exp['variant_conversions'] / vi if vi > 0 else 0.0
        return {
            **exp,
            'control_cvr': round(ctrl_cvr, 4),
            'variant_cvr': round(var_cvr, 4),
            'winner': 'variant' if var_cvr > ctrl_cvr else 'control',
        }

    def get_ab_experiments(self) -> List[Dict]:
        """모든 A/B 실험 목록을 반환한다."""
        return list(self._ab_experiments.values())
