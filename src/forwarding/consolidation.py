"""src/forwarding/consolidation.py — 합배송 관리 (Phase 102)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ConsolidationStatus(Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    EXECUTING = 'executing'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'


@dataclass
class ConsolidationGroup:
    """합배송 그룹."""

    group_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    order_ids: List[str] = field(default_factory=list)
    agent_id: str = ''
    status: ConsolidationStatus = ConsolidationStatus.PENDING
    estimated_weight_kg: float = 0.0
    estimated_cost_usd: float = 0.0
    savings_usd: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None
    metadata: Dict = field(default_factory=dict)


class ConsolidationManager:
    """합배송 그룹 관리 서비스."""

    # 합배송 할인율
    _CONSOLIDATION_DISCOUNT = 0.15

    def __init__(self) -> None:
        self._groups: Dict[str, ConsolidationGroup] = {}

    def create_group(
        self,
        order_ids: List[str],
        agent_id: str,
        estimated_weight_kg: float = 0.0,
    ) -> ConsolidationGroup:
        """합배송 그룹을 생성한다."""
        if not order_ids:
            raise ValueError("order_ids는 비어 있을 수 없습니다.")
        if estimated_weight_kg <= 0:
            estimated_weight_kg = len(order_ids) * 0.5

        savings_data = self.calculate_savings(
            order_ids,
            weight_per_order_kg=estimated_weight_kg / len(order_ids),
        )
        group = ConsolidationGroup(
            order_ids=list(order_ids),
            agent_id=agent_id,
            estimated_weight_kg=estimated_weight_kg,
            estimated_cost_usd=savings_data['consolidated_cost'],
            savings_usd=savings_data['savings'],
        )
        self._groups[group.group_id] = group
        logger.info("합배송 그룹 생성: %s (%d건)", group.group_id, len(order_ids))
        return group

    def get_group(self, group_id: str) -> ConsolidationGroup:
        """합배송 그룹을 조회한다."""
        if group_id not in self._groups:
            raise KeyError(f"합배송 그룹 없음: {group_id}")
        return self._groups[group_id]

    def list_groups(
        self, status: Optional[ConsolidationStatus] = None
    ) -> List[ConsolidationGroup]:
        """합배송 그룹 목록을 반환한다."""
        groups = list(self._groups.values())
        if status is not None:
            groups = [g for g in groups if g.status == status]
        return groups

    def execute_group(self, group_id: str) -> ConsolidationGroup:
        """합배송 그룹을 실행한다."""
        group = self.get_group(group_id)
        if group.status not in (ConsolidationStatus.PENDING, ConsolidationStatus.APPROVED):
            raise ValueError(f"실행할 수 없는 상태: {group.status.value}")

        group.status = ConsolidationStatus.EXECUTING
        try:
            from .agent import ForwardingAgentManager
            mgr = ForwardingAgentManager()
            agent = mgr.get_agent(group.agent_id)
            result = agent.request_consolidation(group.order_ids)
            group.status = ConsolidationStatus.COMPLETED
            group.executed_at = datetime.now(timezone.utc)
            group.metadata['agent_group_id'] = result.get('group_id', '')
            logger.info("합배송 실행 완료: %s", group_id)
        except Exception as exc:
            logger.error("합배송 실행 실패: %s — %s", group_id, exc)
            group.status = ConsolidationStatus.PENDING
            raise
        return group

    def cancel_group(self, group_id: str) -> ConsolidationGroup:
        """합배송 그룹을 취소한다."""
        group = self.get_group(group_id)
        if group.status == ConsolidationStatus.COMPLETED:
            raise ValueError("완료된 그룹은 취소할 수 없습니다.")
        group.status = ConsolidationStatus.CANCELLED
        logger.info("합배송 그룹 취소: %s", group_id)
        return group

    def auto_recommend(
        self,
        order_ids: List[str],
        agent_id: str,
        window_hours: int = 24,
    ) -> Optional[ConsolidationGroup]:
        """주문 목록에 대해 합배송을 자동 추천한다."""
        if len(order_ids) < 2:
            return None
        savings_data = self.calculate_savings(order_ids)
        if savings_data['savings'] <= 0:
            return None
        return self.create_group(order_ids, agent_id)

    def calculate_savings(
        self,
        order_ids: List[str],
        weight_per_order_kg: float = 0.5,
    ) -> Dict:
        """개별 배송 대비 합배송 비용 절감액을 계산한다."""
        from .cost_estimator import CostEstimator
        estimator = CostEstimator()
        individual_total = 0.0
        for _ in order_ids:
            cb = estimator.estimate(weight_per_order_kg, 'KR', 'moltail')
            individual_total += cb.total_usd

        total_weight = len(order_ids) * weight_per_order_kg
        consolidated_cb = estimator.estimate(total_weight, 'KR', 'moltail')
        consolidated_cost = consolidated_cb.total_usd * (1 - self._CONSOLIDATION_DISCOUNT)

        savings = individual_total - consolidated_cost
        savings_pct = (savings / individual_total * 100) if individual_total > 0 else 0.0

        return {
            'individual_cost': round(individual_total, 2),
            'consolidated_cost': round(consolidated_cost, 2),
            'savings': round(max(savings, 0.0), 2),
            'savings_pct': round(max(savings_pct, 0.0), 2),
        }

    def split_shipment(
        self, order_id: str, split_count: int = 2
    ) -> List[Dict]:
        """배송을 여러 건으로 분할한 스펙 목록을 반환한다."""
        if split_count < 2:
            raise ValueError("split_count는 2 이상이어야 합니다.")
        return [
            {
                'split_id': f'{order_id}_split_{i + 1}',
                'order_id': order_id,
                'part': i + 1,
                'total_parts': split_count,
                'weight_fraction': round(1.0 / split_count, 4),
            }
            for i in range(split_count)
        ]
