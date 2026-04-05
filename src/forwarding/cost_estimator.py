"""src/forwarding/cost_estimator.py — 배송 비용 견적 서비스 (Phase 102)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 에이전트별 기본 설정
_AGENT_CONFIG = {
    'moltail': {
        'rate_per_kg': 6.0,
        'min_charge': 10.0,
        'agent_fee': 3.0,
    },
    'ihanex': {
        'rate_per_kg': 5.5,
        'min_charge': 9.0,
        'agent_fee': 2.5,
    },
}

# 소액 면세 기준 (USD)
_CUSTOMS_THRESHOLD = 150.0


@dataclass
class CostBreakdown:
    """배송 비용 세부 내역."""

    base_shipping_usd: float
    fuel_surcharge_usd: float
    insurance_usd: float
    agent_fee_usd: float
    customs_duty_usd: float
    vat_usd: float
    total_usd: float
    currency: str = 'USD'


class CostEstimator:
    """배송 비용 견적 서비스."""

    _duty_rates: Dict[str, float] = {
        'electronics': 0.08,
        'clothing': 0.13,
        'default': 0.08,
    }
    _vat_rate: float = 0.10

    def estimate(
        self,
        weight_kg: float,
        country: str,
        agent_id: str,
        product_value_usd: float = 0.0,
        category: str = 'default',
        service: str = 'standard',
    ) -> CostBreakdown:
        """배송 비용 전체를 견적한다."""
        cfg = _AGENT_CONFIG.get(agent_id, _AGENT_CONFIG['moltail'])
        rate = cfg['rate_per_kg']
        if service == 'express':
            rate *= 1.5

        base = max(weight_kg * rate, cfg['min_charge'])
        fuel = round(base * 0.10, 2)
        insurance = round(product_value_usd * 0.01, 2)
        agent_fee = cfg['agent_fee']

        # 소액 면세 적용
        if product_value_usd < _CUSTOMS_THRESHOLD:
            duty = 0.0
            vat = 0.0
        else:
            duty_rate = self._duty_rates.get(category, self._duty_rates['default'])
            duty = round(product_value_usd * duty_rate, 2)
            vat = round((product_value_usd + duty) * self._vat_rate, 2)

        total = round(base + fuel + insurance + agent_fee + duty + vat, 2)

        return CostBreakdown(
            base_shipping_usd=round(base, 2),
            fuel_surcharge_usd=fuel,
            insurance_usd=insurance,
            agent_fee_usd=agent_fee,
            customs_duty_usd=duty,
            vat_usd=vat,
            total_usd=total,
        )

    def simulate_consolidation(
        self, weights: List[float], country: str, agent_id: str
    ) -> Dict:
        """개별 배송과 합배송 비용을 비교한다."""
        individual_costs = [
            self.estimate(w, country, agent_id).total_usd for w in weights
        ]
        individual_total = sum(individual_costs)
        consolidated_total = self.estimate(sum(weights), country, agent_id).total_usd
        # 합배송 15% 할인
        consolidated_discounted = round(consolidated_total * 0.85, 2)
        savings = round(individual_total - consolidated_discounted, 2)

        return {
            'individual_costs': [round(c, 2) for c in individual_costs],
            'individual_total': round(individual_total, 2),
            'consolidated_cost': consolidated_discounted,
            'savings': max(savings, 0.0),
            'savings_pct': round(
                max(savings, 0.0) / individual_total * 100 if individual_total > 0 else 0.0,
                2,
            ),
        }

    def get_cheapest_agent(
        self,
        weight_kg: float,
        country: str,
        product_value_usd: float = 0.0,
    ) -> Dict:
        """가장 저렴한 에이전트를 반환한다."""
        results = {}
        for agent_id in _AGENT_CONFIG:
            cb = self.estimate(weight_kg, country, agent_id, product_value_usd)
            results[agent_id] = cb

        cheapest_id = min(results, key=lambda k: results[k].total_usd)
        most_expensive_id = max(results, key=lambda k: results[k].total_usd)
        savings = round(
            results[most_expensive_id].total_usd - results[cheapest_id].total_usd, 2
        )

        return {
            'agent_id': cheapest_id,
            'cost': results[cheapest_id],
            'savings_vs_expensive': savings,
        }
