"""src/autonomous_ops/simulation.py — 시뮬레이션 엔진 (Phase 106)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class ScenarioType(str, Enum):
    price_crash = 'price_crash'
    demand_surge = 'demand_surge'
    supply_disruption = 'supply_disruption'
    currency_shock = 'currency_shock'
    system_failure = 'system_failure'
    competitor_action = 'competitor_action'


class SimulationStatus(str, Enum):
    pending = 'pending'
    running = 'running'
    completed = 'completed'
    failed = 'failed'


@dataclass
class Scenario:
    scenario_id: str
    name: str
    type: ScenarioType
    parameters: Dict
    duration_hours: float
    created_at: str

    def to_dict(self) -> Dict:
        return {
            'scenario_id': self.scenario_id,
            'name': self.name,
            'type': self.type.value,
            'parameters': self.parameters,
            'duration_hours': self.duration_hours,
            'created_at': self.created_at,
        }


@dataclass
class SimulationResult:
    result_id: str
    scenario_id: str
    status: SimulationStatus
    revenue_impact: float
    cost_impact: float
    order_impact: int
    risk_score: float
    recommendations: List[str]
    completed_at: str

    def to_dict(self) -> Dict:
        return {
            'result_id': self.result_id,
            'scenario_id': self.scenario_id,
            'status': self.status.value,
            'revenue_impact': self.revenue_impact,
            'cost_impact': self.cost_impact,
            'order_impact': self.order_impact,
            'risk_score': self.risk_score,
            'recommendations': self.recommendations,
            'completed_at': self.completed_at,
        }


class SimulationEngine:
    """시나리오 시뮬레이션 및 What-if 분석."""

    def __init__(self) -> None:
        self._scenarios: Dict[str, Scenario] = {}
        self._results: Dict[str, SimulationResult] = {}

    def create_scenario(
        self,
        name: str,
        type: ScenarioType,
        parameters: Dict,
        duration_hours: float = 24.0,
    ) -> Scenario:
        scenario = Scenario(
            scenario_id=f'scn_{uuid.uuid4().hex[:10]}',
            name=name,
            type=type,
            parameters=parameters,
            duration_hours=duration_hours,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._scenarios[scenario.scenario_id] = scenario
        return scenario

    def run_simulation(self, scenario_id: str, base_metrics: Dict) -> SimulationResult:
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            raise KeyError(f'시나리오를 찾을 수 없습니다: {scenario_id}')

        base_revenue = float(base_metrics.get('revenue', 1_000_000))
        base_cost = float(base_metrics.get('cost', 700_000))
        base_orders = int(base_metrics.get('orders', 100))

        revenue_impact, cost_impact, order_impact, risk_score, recs = self._calculate_impact(
            scenario, base_revenue, base_cost, base_orders
        )

        result = SimulationResult(
            result_id=f'res_{uuid.uuid4().hex[:10]}',
            scenario_id=scenario_id,
            status=SimulationStatus.completed,
            revenue_impact=round(revenue_impact, 2),
            cost_impact=round(cost_impact, 2),
            order_impact=order_impact,
            risk_score=round(risk_score, 2),
            recommendations=recs,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        self._results[result.result_id] = result
        return result

    def get_scenario(self, scenario_id: str) -> Optional[Scenario]:
        return self._scenarios.get(scenario_id)

    def get_result(self, result_id: str) -> Optional[SimulationResult]:
        return self._results.get(result_id)

    def list_scenarios(self) -> List[Dict]:
        return [s.to_dict() for s in self._scenarios.values()]

    def list_results(self) -> List[Dict]:
        return [r.to_dict() for r in self._results.values()]

    def what_if_analysis(
        self,
        base_revenue: float,
        price_change_pct: float = 0,
        demand_change_pct: float = 0,
        cost_change_pct: float = 0,
        fx_change_pct: float = 0,
    ) -> Dict:
        adj_revenue = base_revenue * (1 + price_change_pct / 100) * (1 + demand_change_pct / 100)
        adj_cost = base_revenue * 0.7 * (1 + cost_change_pct / 100) * (1 + fx_change_pct / 100)
        net = adj_revenue - adj_cost
        margin = (adj_revenue - adj_cost) / adj_revenue if adj_revenue else 0.0
        return {
            'base_revenue': base_revenue,
            'adjusted_revenue': round(adj_revenue, 2),
            'adjusted_cost': round(adj_cost, 2),
            'net_profit': round(net, 2),
            'margin_rate': round(margin, 4),
            'price_change_pct': price_change_pct,
            'demand_change_pct': demand_change_pct,
            'cost_change_pct': cost_change_pct,
            'fx_change_pct': fx_change_pct,
        }

    # ── 내부 ──────────────────────────────────────────────────────────────────

    def _calculate_impact(
        self, scenario: Scenario, base_revenue: float, base_cost: float, base_orders: int
    ):
        p = scenario.parameters
        stype = scenario.type

        if stype == ScenarioType.price_crash:
            crash_pct = float(p.get('crash_pct', -20))
            revenue_impact = base_revenue * (crash_pct / 100)
            order_impact = int(base_orders * abs(crash_pct) / 100 * 0.5)
            cost_impact = 0.0
            risk_score = min(100.0, abs(crash_pct) * 2)
            recs = ['가격 하락 대응 전략 수립', '경쟁사 가격 모니터링 강화']

        elif stype == ScenarioType.demand_surge:
            surge_pct = float(p.get('surge_pct', 50))
            revenue_impact = base_revenue * (surge_pct / 100)
            order_impact = int(base_orders * surge_pct / 100)
            cost_impact = base_cost * (surge_pct / 100) * 0.8
            risk_score = min(100.0, surge_pct * 0.5)
            recs = ['재고 확보 검토', '물류 용량 확장 검토']

        elif stype == ScenarioType.supply_disruption:
            disruption_pct = float(p.get('disruption_pct', 30))
            revenue_impact = -base_revenue * (disruption_pct / 100)
            order_impact = -int(base_orders * disruption_pct / 100)
            cost_impact = base_cost * (disruption_pct / 100) * 0.3
            risk_score = min(100.0, disruption_pct * 2.5)
            recs = ['대체 공급처 확보', '재고 비축 전략 수립']

        elif stype == ScenarioType.currency_shock:
            fx_change_pct = float(p.get('fx_change_pct', 10))
            revenue_impact = base_revenue * (fx_change_pct / 100) * 0.3
            cost_impact = base_cost * (fx_change_pct / 100)
            order_impact = 0
            risk_score = min(100.0, abs(fx_change_pct) * 3)
            recs = ['환율 헤지 전략 검토', '가격 정책 재검토']

        elif stype == ScenarioType.system_failure:
            failure_duration_h = float(p.get('duration_hours', 4))
            revenue_impact = -base_revenue * (failure_duration_h / 24) * 0.9
            cost_impact = base_cost * 0.1
            order_impact = -int(base_orders * failure_duration_h / 24)
            risk_score = min(100.0, failure_duration_h * 10)
            recs = ['장애 복구 절차 점검', '백업 시스템 활성화']

        else:  # competitor_action
            impact_pct = float(p.get('impact_pct', -10))
            revenue_impact = base_revenue * (impact_pct / 100)
            cost_impact = 0.0
            order_impact = int(base_orders * impact_pct / 100)
            risk_score = min(100.0, abs(impact_pct) * 2)
            recs = ['경쟁사 전략 분석', '차별화 전략 강화']

        return revenue_impact, cost_impact, order_impact, risk_score, recs
