"""src/china_marketplace/agent_manager.py — 구매대행 에이전트 관리 (Phase 104)."""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PurchasingAgent(ABC):
    """구매대행 에이전트 인터페이스 (ABC)."""

    @abstractmethod
    def search(self, keyword: str, **kwargs) -> List[Dict]:
        """상품 검색."""

    @abstractmethod
    def get_detail(self, product_id: str) -> Dict:
        """상품 상세 조회."""

    @abstractmethod
    def verify_seller(self, seller_id: str) -> Dict:
        """셀러 검증."""

    @abstractmethod
    def place_order(self, product_id: str, quantity: int, **kwargs) -> Dict:
        """주문 생성."""

    @abstractmethod
    def track_order(self, order_id: str) -> Dict:
        """주문 추적."""


@dataclass
class AgentRecord:
    agent_id: str
    name: str
    marketplace: str  # 'taobao' | '1688' | 'all'
    specialties: List[str] = field(default_factory=list)  # ['clothing', 'electronics', 'food', ...]
    is_active: bool = True
    orders_processed: int = 0
    success_count: int = 0
    avg_processing_hours: float = 0.0
    accuracy_rate: float = 1.0
    response_rate: float = 1.0
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def success_rate(self) -> float:
        if self.orders_processed == 0:
            return 1.0
        return round(self.success_count / self.orders_processed, 4)

    @property
    def overall_score(self) -> float:
        return round(
            self.success_rate * 0.4 +
            self.accuracy_rate * 0.3 +
            self.response_rate * 0.3,
            4,
        )

    def record_completion(self, success: bool, processing_hours: float) -> None:
        self.orders_processed += 1
        if success:
            self.success_count += 1
        # 이동 평균 처리 시간
        n = self.orders_processed
        self.avg_processing_hours = round(
            (self.avg_processing_hours * (n - 1) + processing_hours) / n, 2
        )

    def to_dict(self) -> Dict:
        return {
            'agent_id': self.agent_id,
            'name': self.name,
            'marketplace': self.marketplace,
            'specialties': self.specialties,
            'is_active': self.is_active,
            'orders_processed': self.orders_processed,
            'success_count': self.success_count,
            'success_rate': self.success_rate,
            'avg_processing_hours': self.avg_processing_hours,
            'accuracy_rate': self.accuracy_rate,
            'response_rate': self.response_rate,
            'overall_score': self.overall_score,
            'registered_at': self.registered_at,
        }


class AgentManager:
    """구매대행 에이전트 등록/관리 및 주문 배정."""

    def __init__(self):
        self._agents: Dict[str, AgentRecord] = {}
        self._assignments: Dict[str, str] = {}  # order_id → agent_id
        self._seed_default_agents()

    def _seed_default_agents(self) -> None:
        """기본 에이전트 등록."""
        defaults = [
            AgentRecord(
                agent_id='agent_taobao_001',
                name='타오바오 전문 에이전트 A',
                marketplace='taobao',
                specialties=['clothing', 'accessories', 'home'],
                accuracy_rate=0.96,
                response_rate=0.98,
            ),
            AgentRecord(
                agent_id='agent_taobao_002',
                name='타오바오 전문 에이전트 B',
                marketplace='taobao',
                specialties=['electronics', 'gadgets'],
                accuracy_rate=0.94,
                response_rate=0.97,
            ),
            AgentRecord(
                agent_id='agent_1688_001',
                name='1688 전문 에이전트 A',
                marketplace='1688',
                specialties=['manufacturing', 'bulk', 'food'],
                accuracy_rate=0.95,
                response_rate=0.96,
            ),
            AgentRecord(
                agent_id='agent_all_001',
                name='통합 에이전트 A',
                marketplace='all',
                specialties=['clothing', 'electronics', 'home', 'food'],
                accuracy_rate=0.93,
                response_rate=0.95,
            ),
        ]
        for agent in defaults:
            self._agents[agent.agent_id] = agent

    # ── 에이전트 등록/조회 ───────────────────────────────────────────────────

    def register_agent(
        self,
        name: str,
        marketplace: str,
        specialties: Optional[List[str]] = None,
    ) -> AgentRecord:
        agent_id = f'agent_{uuid.uuid4().hex[:8]}'
        agent = AgentRecord(
            agent_id=agent_id,
            name=name,
            marketplace=marketplace,
            specialties=specialties or [],
        )
        self._agents[agent_id] = agent
        logger.info("에이전트 등록: %s (%s)", name, agent_id)
        return agent

    def get_agent(self, agent_id: str) -> Optional[AgentRecord]:
        return self._agents.get(agent_id)

    def list_agents(self, marketplace: Optional[str] = None, active_only: bool = True) -> List[AgentRecord]:
        agents = list(self._agents.values())
        if active_only:
            agents = [a for a in agents if a.is_active]
        if marketplace:
            agents = [a for a in agents if a.marketplace in (marketplace, 'all')]
        return agents

    def deactivate_agent(self, agent_id: str) -> AgentRecord:
        agent = self._agents[agent_id]
        agent.is_active = False
        return agent

    # ── 에이전트 배정 ────────────────────────────────────────────────────────

    def assign_best_agent(self, order_id: str, marketplace: str, category: Optional[str] = None) -> Optional[AgentRecord]:
        """최적 에이전트 배정 (전문분야 + 성과점수 기반)."""
        candidates = self.list_agents(marketplace=marketplace)
        if not candidates:
            return None
        if category:
            specialists = [a for a in candidates if category in a.specialties]
            if specialists:
                candidates = specialists
        # 성과 점수 기준 정렬
        best = max(candidates, key=lambda a: a.overall_score)
        self._assignments[order_id] = best.agent_id
        logger.info("에이전트 배정: 주문 %s → 에이전트 %s", order_id, best.agent_id)
        return best

    def assign_agent(self, order_id: str, agent_id: str) -> AgentRecord:
        """특정 에이전트 배정."""
        if agent_id not in self._agents:
            raise KeyError(f'에이전트를 찾을 수 없습니다: {agent_id}')
        self._assignments[order_id] = agent_id
        return self._agents[agent_id]

    def get_assignment(self, order_id: str) -> Optional[str]:
        return self._assignments.get(order_id)

    # ── 성과 기록 ────────────────────────────────────────────────────────────

    def record_completion(self, order_id: str, success: bool, processing_hours: float = 24.0) -> None:
        agent_id = self._assignments.get(order_id)
        if agent_id and agent_id in self._agents:
            self._agents[agent_id].record_completion(success, processing_hours)

    def get_performance_stats(self) -> Dict:
        agents = list(self._agents.values())
        if not agents:
            return {'total': 0, 'agents': []}
        return {
            'total': len(agents),
            'active': sum(1 for a in agents if a.is_active),
            'agents': [a.to_dict() for a in sorted(agents, key=lambda a: a.overall_score, reverse=True)],
        }
