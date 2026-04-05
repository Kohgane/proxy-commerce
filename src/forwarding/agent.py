"""src/forwarding/agent.py — 배송대행지 에이전트 ABC 및 구현 (Phase 102)."""
from __future__ import annotations

import abc
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ForwardingAgent(abc.ABC):
    """배송대행지 에이전트 추상 기반 클래스."""

    @abc.abstractmethod
    def check_incoming(self, tracking_number: str) -> Dict:
        """입고 현황을 확인한다."""

    @abc.abstractmethod
    def request_consolidation(self, order_ids: List[str]) -> Dict:
        """합배송을 요청한다."""

    @abc.abstractmethod
    def request_shipment(self, group_id: str, address: Dict) -> Dict:
        """배송을 요청한다."""

    @abc.abstractmethod
    def get_tracking(self, shipment_id: str) -> Dict:
        """배송 추적 정보를 조회한다."""

    @abc.abstractmethod
    def get_warehouse_address(self, country: str) -> Dict:
        """창고 주소를 반환한다."""

    @abc.abstractmethod
    def estimate_shipping_cost(
        self, weight_kg: float, country: str, service: str = 'standard'
    ) -> Dict:
        """배송 비용을 견적한다."""

    @property
    @abc.abstractmethod
    def agent_id(self) -> str:
        """에이전트 ID."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """에이전트 이름."""

    @property
    @abc.abstractmethod
    def reliability_score(self) -> float:
        """신뢰도 점수 (0.0 ~ 1.0)."""


# ---------------------------------------------------------------------------
# MoltailAgent
# ---------------------------------------------------------------------------

class MoltailAgent(ForwardingAgent):
    """몰테일 배송대행지 에이전트 (mock 구현)."""

    _WAREHOUSE_ADDRESSES = {
        'US': {
            'name': '몰테일 미국 창고',
            'address': '20 Corporate Park, Suite 100',
            'city': 'Irvine',
            'state': 'CA',
            'zip': '92606',
            'country': 'USA',
            'full': '20 Corporate Park, Suite 100, Irvine, CA 92606, USA',
        },
        'JP': {
            'name': '몰테일 일본 창고',
            'address': '城見1丁目2番27号',
            'city': '大阪市中央区',
            'zip': '540-0001',
            'country': 'JP',
            'full': '〒540-0001 大阪府大阪市中央区城見1丁目2番27号',
        },
    }

    _RATE_USD_PER_KG = {'US': 6.5, 'JP': 5.8}
    _MIN_CHARGE = {'US': 10.0, 'JP': 9.0}

    @property
    def agent_id(self) -> str:
        return 'moltail'

    @property
    def name(self) -> str:
        return '몰테일'

    @property
    def reliability_score(self) -> float:
        return 0.95

    def check_incoming(self, tracking_number: str) -> Dict:
        now = datetime.now(timezone.utc)
        return {
            'tracking_number': tracking_number,
            'status': 'received',
            'agent_id': self.agent_id,
            'weight_kg': 0.8,
            'received_at': now.isoformat(),
            'photo_urls': [
                f'https://moltail.com/photos/{tracking_number}_1.jpg',
                f'https://moltail.com/photos/{tracking_number}_2.jpg',
            ],
            'inspection_notes': '정상 입고',
            'issue_type': None,
        }

    def request_consolidation(self, order_ids: List[str]) -> Dict:
        group_id = f'moltail_grp_{uuid.uuid4().hex[:8]}'
        return {
            'group_id': group_id,
            'order_ids': order_ids,
            'agent_id': self.agent_id,
            'status': 'approved',
            'estimated_weight_kg': len(order_ids) * 0.7,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

    def request_shipment(self, group_id: str, address: Dict) -> Dict:
        shipment_id = f'moltail_ship_{uuid.uuid4().hex[:8]}'
        tracking = f'MT{uuid.uuid4().hex[:12].upper()}'
        return {
            'shipment_id': shipment_id,
            'group_id': group_id,
            'tracking_number': tracking,
            'agent_id': self.agent_id,
            'status': 'shipped',
            'estimated_delivery_days': 7,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

    def get_tracking(self, shipment_id: str) -> Dict:
        now = datetime.now(timezone.utc)
        return {
            'shipment_id': shipment_id,
            'agent_id': self.agent_id,
            'status': 'domestic_transit',
            'events': [
                {
                    'timestamp': now.isoformat(),
                    'status': 'domestic_transit',
                    'location': '인천 국제우편물류센터',
                    'description': '국내 배송 중',
                },
                {
                    'timestamp': now.isoformat(),
                    'status': 'customs_clearance',
                    'location': '인천공항 세관',
                    'description': '통관 완료',
                },
            ],
            'customs_status': 'cleared',
        }

    def get_warehouse_address(self, country: str) -> Dict:
        country_upper = country.upper()
        return self._WAREHOUSE_ADDRESSES.get(
            country_upper,
            self._WAREHOUSE_ADDRESSES['US'],
        )

    def estimate_shipping_cost(
        self, weight_kg: float, country: str, service: str = 'standard'
    ) -> Dict:
        country_upper = country.upper()
        rate = self._RATE_USD_PER_KG.get(country_upper, self._RATE_USD_PER_KG['US'])
        min_charge = self._MIN_CHARGE.get(country_upper, self._MIN_CHARGE['US'])
        if service == 'express':
            rate *= 1.5
        cost = max(weight_kg * rate, min_charge)
        return {
            'agent_id': self.agent_id,
            'weight_kg': weight_kg,
            'country': country_upper,
            'service': service,
            'cost_usd': round(cost, 2),
            'rate_per_kg': rate,
            'currency': 'USD',
        }


# ---------------------------------------------------------------------------
# IhanexAgent
# ---------------------------------------------------------------------------

class IhanexAgent(ForwardingAgent):
    """이하넥스 배송대행지 에이전트 (mock 구현)."""

    _WAREHOUSE_ADDRESSES = {
        'US': {
            'name': '이하넥스 미국 창고',
            'address': '3003 Commerce St',
            'city': 'Dallas',
            'state': 'TX',
            'zip': '75226',
            'country': 'USA',
            'full': '3003 Commerce St, Dallas, TX 75226, USA',
        },
        'JP': {
            'name': '이하넥스 일본 창고',
            'address': '有明3丁目7番26号',
            'city': '東京都江東区',
            'zip': '135-0063',
            'country': 'JP',
            'full': '〒135-0063 東京都江東区有明3丁目7番26号',
        },
    }

    _RATE_USD_PER_KG = {'US': 5.8, 'JP': 5.2}
    _MIN_CHARGE = {'US': 9.0, 'JP': 8.5}

    @property
    def agent_id(self) -> str:
        return 'ihanex'

    @property
    def name(self) -> str:
        return '이하넥스'

    @property
    def reliability_score(self) -> float:
        return 0.88

    def check_incoming(self, tracking_number: str) -> Dict:
        now = datetime.now(timezone.utc)
        return {
            'tracking_number': tracking_number,
            'status': 'received',
            'agent_id': self.agent_id,
            'weight_kg': 0.75,
            'received_at': now.isoformat(),
            'photo_urls': [
                f'https://ihanex.com/photos/{tracking_number}_1.jpg',
            ],
            'inspection_notes': '정상 입고',
            'issue_type': None,
        }

    def request_consolidation(self, order_ids: List[str]) -> Dict:
        group_id = f'ihanex_grp_{uuid.uuid4().hex[:8]}'
        return {
            'group_id': group_id,
            'order_ids': order_ids,
            'agent_id': self.agent_id,
            'status': 'approved',
            'estimated_weight_kg': len(order_ids) * 0.65,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

    def request_shipment(self, group_id: str, address: Dict) -> Dict:
        shipment_id = f'ihanex_ship_{uuid.uuid4().hex[:8]}'
        tracking = f'IH{uuid.uuid4().hex[:12].upper()}'
        return {
            'shipment_id': shipment_id,
            'group_id': group_id,
            'tracking_number': tracking,
            'agent_id': self.agent_id,
            'status': 'shipped',
            'estimated_delivery_days': 9,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

    def get_tracking(self, shipment_id: str) -> Dict:
        now = datetime.now(timezone.utc)
        return {
            'shipment_id': shipment_id,
            'agent_id': self.agent_id,
            'status': 'customs_clearance',
            'events': [
                {
                    'timestamp': now.isoformat(),
                    'status': 'customs_clearance',
                    'location': '인천공항 세관',
                    'description': '통관 진행 중',
                },
            ],
            'customs_status': 'in_progress',
        }

    def get_warehouse_address(self, country: str) -> Dict:
        country_upper = country.upper()
        return self._WAREHOUSE_ADDRESSES.get(
            country_upper,
            self._WAREHOUSE_ADDRESSES['US'],
        )

    def estimate_shipping_cost(
        self, weight_kg: float, country: str, service: str = 'standard'
    ) -> Dict:
        country_upper = country.upper()
        rate = self._RATE_USD_PER_KG.get(country_upper, self._RATE_USD_PER_KG['US'])
        min_charge = self._MIN_CHARGE.get(country_upper, self._MIN_CHARGE['US'])
        if service == 'express':
            rate *= 1.4
        cost = max(weight_kg * rate, min_charge)
        return {
            'agent_id': self.agent_id,
            'weight_kg': weight_kg,
            'country': country_upper,
            'service': service,
            'cost_usd': round(cost, 2),
            'rate_per_kg': rate,
            'currency': 'USD',
        }


# ---------------------------------------------------------------------------
# ForwardingAgentManager
# ---------------------------------------------------------------------------

class ForwardingAgentManager:
    """배송대행지 에이전트 관리자."""

    def __init__(self) -> None:
        self._agents: Dict[str, ForwardingAgent] = {}
        self.register_agent(MoltailAgent())
        self.register_agent(IhanexAgent())

    def register_agent(self, agent: ForwardingAgent) -> None:
        """에이전트를 등록한다."""
        self._agents[agent.agent_id] = agent
        logger.debug("배송대행지 에이전트 등록: %s", agent.agent_id)

    def get_agent(self, agent_id: str) -> ForwardingAgent:
        """에이전트를 조회한다."""
        if agent_id not in self._agents:
            raise KeyError(f"알 수 없는 에이전트: {agent_id}")
        return self._agents[agent_id]

    def list_agents(self) -> List[Dict]:
        """등록된 에이전트 목록을 반환한다."""
        return [
            {
                'agent_id': a.agent_id,
                'name': a.name,
                'reliability': a.reliability_score,
            }
            for a in self._agents.values()
        ]

    def recommend_agent(self, priority: str = 'balanced') -> ForwardingAgent:
        """우선순위에 따라 최적 에이전트를 추천한다.

        priority options: 'cost', 'speed', 'reliability', 'balanced'
        """
        agents = list(self._agents.values())
        if not agents:
            raise RuntimeError("등록된 에이전트가 없습니다.")

        if priority == 'reliability':
            return max(agents, key=lambda a: a.reliability_score)

        if priority == 'cost':
            # 이하넥스가 더 저렴
            costs = {
                a.agent_id: a.estimate_shipping_cost(1.0, 'US')['cost_usd']
                for a in agents
            }
            return min(agents, key=lambda a: costs[a.agent_id])

        if priority == 'speed':
            # 몰테일이 더 빠름 (배송일 기준 7 vs 9)
            speed_scores = {'moltail': 9, 'ihanex': 7}
            return max(agents, key=lambda a: speed_scores.get(a.agent_id, 5))

        # balanced: reliability 40% + cost 30% + speed 30%
        def balanced_score(a: ForwardingAgent) -> float:
            cost = a.estimate_shipping_cost(1.0, 'US')['cost_usd']
            cost_score = 1.0 / (cost + 1)
            speed_map = {'moltail': 0.9, 'ihanex': 0.7}
            speed_score = speed_map.get(a.agent_id, 0.5)
            return a.reliability_score * 0.4 + cost_score * 10 * 0.3 + speed_score * 0.3

        return max(agents, key=balanced_score)
