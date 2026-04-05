"""src/forwarding/dashboard.py — 배송대행 대시보드 (Phase 102)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ForwardingDashboard:
    """배송대행 통합 대시보드."""

    def __init__(
        self,
        verifier=None,
        manager=None,
        tracker=None,
        estimator=None,
        agent_manager=None,
    ) -> None:
        self._verifier = verifier
        self._manager = manager
        self._tracker = tracker
        self._estimator = estimator
        self._agent_manager = agent_manager

    def get_summary(self) -> Dict:
        """전체 배송대행 현황 요약을 반환한다."""
        incoming_stats: Dict = {}
        consolidation_stats: Dict = {'pending': 0, 'completed': 0, 'total_savings_usd': 0.0, 'total_groups': 0}
        shipment_stats: Dict = {'pending': 0, 'in_transit': 0, 'delivered': 0}
        total_shipments = 0

        if self._verifier is not None:
            incoming_stats = self._verifier.get_stats()

        if self._manager is not None:
            from .consolidation import ConsolidationStatus
            groups = self._manager.list_groups()
            consolidation_stats['total_groups'] = len(groups)
            for g in groups:
                if g.status == ConsolidationStatus.PENDING:
                    consolidation_stats['pending'] += 1
                elif g.status == ConsolidationStatus.COMPLETED:
                    consolidation_stats['completed'] += 1
                    consolidation_stats['total_savings_usd'] += g.savings_usd

        if self._tracker is not None:
            from .tracker import ShipmentStatus
            shipments = self._tracker.list_shipments()
            total_shipments = len(shipments)
            for s in shipments:
                if s.status == ShipmentStatus.PENDING:
                    shipment_stats['pending'] += 1
                elif s.status == ShipmentStatus.DELIVERED:
                    shipment_stats['delivered'] += 1
                else:
                    shipment_stats['in_transit'] += 1

        return {
            'incoming_stats': incoming_stats,
            'consolidation_stats': consolidation_stats,
            'shipment_stats': shipment_stats,
            'total_shipments': total_shipments,
        }

    def get_agent_stats(self) -> List[Dict]:
        """에이전트별 통계를 반환한다."""
        if self._agent_manager is None:
            from .agent import ForwardingAgentManager
            agent_manager = ForwardingAgentManager()
        else:
            agent_manager = self._agent_manager

        stats = []
        for info in agent_manager.list_agents():
            agent_id = info['agent_id']
            key_us = f'{agent_id}_US'
            avg_days_map = {'moltail_US': 7, 'moltail_JP': 5, 'ihanex_US': 9, 'ihanex_JP': 6}
            avg_days = avg_days_map.get(key_us, 10)
            stats.append({
                'agent_id': agent_id,
                'name': info.get('name', agent_id),
                'reliability': info.get('reliability', 0.0),
                'avg_processing_days': avg_days,
            })
        return stats

    def get_cost_stats(self, days: int = 30) -> Dict:
        """기간별 비용 통계를 반환한다."""
        if self._tracker is None:
            return {'total_cost_usd': 0.0, 'avg_cost_per_shipment_usd': 0.0, 'by_agent': {}}

        shipments = self._tracker.list_shipments()
        total = 0.0
        by_agent: Dict[str, float] = {}

        if self._estimator is not None:
            for s in shipments:
                cb = self._estimator.estimate(0.8, 'KR', s.agent_id)
                total += cb.total_usd
                by_agent[s.agent_id] = by_agent.get(s.agent_id, 0.0) + cb.total_usd

        avg = total / len(shipments) if shipments else 0.0
        return {
            'total_cost_usd': round(total, 2),
            'avg_cost_per_shipment_usd': round(avg, 2),
            'by_agent': {k: round(v, 2) for k, v in by_agent.items()},
        }
