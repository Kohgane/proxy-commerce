"""src/live_chat/agent_assignment.py — 상담원 배정 서비스 (Phase 107)."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    online = 'online'
    busy = 'busy'
    away = 'away'
    offline = 'offline'


@dataclass
class AgentProfile:
    agent_id: str
    name: str
    status: AgentStatus = AgentStatus.online
    skills: List[str] = field(default_factory=list)
    current_sessions: int = 0
    max_sessions: int = 5
    languages: List[str] = field(default_factory=list)
    rating: float = 5.0
    shift: str = '09:00-18:00'

    @property
    def is_available(self) -> bool:
        return (
            self.status == AgentStatus.online
            and self.current_sessions < self.max_sessions
        )

    @property
    def load_ratio(self) -> float:
        if self.max_sessions == 0:
            return 1.0
        return self.current_sessions / self.max_sessions

    def to_dict(self) -> dict:
        return {
            'agent_id': self.agent_id,
            'name': self.name,
            'status': self.status.value if hasattr(self.status, 'value') else self.status,
            'skills': self.skills,
            'current_sessions': self.current_sessions,
            'max_sessions': self.max_sessions,
            'languages': self.languages,
            'rating': self.rating,
            'shift': self.shift,
            'is_available': self.is_available,
            'load_ratio': round(self.load_ratio, 2),
        }


# ── 배정 전략 ─────────────────────────────────────────────────────────────────

class AssignmentStrategy(ABC):
    @abstractmethod
    def assign(
        self,
        agents: List[AgentProfile],
        customer_id: str,
        tags: Optional[List[str]] = None,
        is_vip: bool = False,
    ) -> Optional[AgentProfile]:
        """사용 가능한 상담원 목록에서 배정할 상담원 선택."""


class RoundRobinStrategy(AssignmentStrategy):
    """순차 배정."""

    def __init__(self):
        self._index = 0

    def assign(self, agents, customer_id, tags=None, is_vip=False):
        available = [a for a in agents if a.is_available]
        if not available:
            return None
        agent = available[self._index % len(available)]
        self._index += 1
        return agent


class LeastLoadStrategy(AssignmentStrategy):
    """최소 부하 배정."""

    def assign(self, agents, customer_id, tags=None, is_vip=False):
        available = [a for a in agents if a.is_available]
        if not available:
            return None
        return min(available, key=lambda a: a.load_ratio)


class SkillBasedStrategy(AssignmentStrategy):
    """스킬 기반 배정 — 문의 유형 ↔ 상담원 전문분야 매칭."""

    def assign(self, agents, customer_id, tags=None, is_vip=False):
        available = [a for a in agents if a.is_available]
        if not available:
            return None
        if not tags:
            return min(available, key=lambda a: a.load_ratio)
        # 태그 매칭 점수 계산
        def skill_score(agent: AgentProfile) -> int:
            return sum(1 for t in (tags or []) if t in agent.skills)
        best = max(available, key=skill_score)
        return best


class PriorityStrategy(AssignmentStrategy):
    """VIP 고객 우선 배정 — 평점 높은 상담원."""

    def assign(self, agents, customer_id, tags=None, is_vip=False):
        available = [a for a in agents if a.is_available]
        if not available:
            return None
        if is_vip:
            return max(available, key=lambda a: a.rating)
        return min(available, key=lambda a: a.load_ratio)


# ── 대기열 항목 ───────────────────────────────────────────────────────────────

@dataclass
class QueueEntry:
    session_id: str
    customer_id: str
    priority: int = 0  # 높을수록 우선
    tags: List[str] = field(default_factory=list)
    is_vip: bool = False
    enqueued_at: str = ''

    def __post_init__(self):
        if not self.enqueued_at:
            from datetime import datetime, timezone
            self.enqueued_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'customer_id': self.customer_id,
            'priority': self.priority,
            'tags': self.tags,
            'is_vip': self.is_vip,
            'enqueued_at': self.enqueued_at,
        }


# ── 상담원 배정 서비스 ─────────────────────────────────────────────────────────

class AgentAssignmentService:
    """상담원 배정 + 대기열 관리."""

    def __init__(self, strategy: Optional[AssignmentStrategy] = None):
        self._agents: Dict[str, AgentProfile] = {}
        self._strategy: AssignmentStrategy = strategy or LeastLoadStrategy()
        self._queue: List[QueueEntry] = []

    # ── 상담원 등록/관리 ───────────────────────────────────────────────────────

    def register_agent(self, agent: AgentProfile) -> AgentProfile:
        self._agents[agent.agent_id] = agent
        logger.info("상담원 등록: %s (%s)", agent.agent_id, agent.name)
        return agent

    def get_agent(self, agent_id: str) -> Optional[AgentProfile]:
        return self._agents.get(agent_id)

    def list_agents(self, status: Optional[AgentStatus] = None) -> List[AgentProfile]:
        agents = list(self._agents.values())
        if status:
            agents = [a for a in agents if a.status == status]
        return agents

    def update_agent_status(self, agent_id: str, status: AgentStatus) -> Optional[AgentProfile]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        agent.status = status
        return agent

    def set_strategy(self, strategy: AssignmentStrategy) -> None:
        self._strategy = strategy

    # ── 배정 ──────────────────────────────────────────────────────────────────

    def assign(
        self,
        session_id: str,
        customer_id: str,
        tags: Optional[List[str]] = None,
        is_vip: bool = False,
    ) -> Optional[AgentProfile]:
        available = [a for a in self._agents.values() if a.is_available]
        if not available:
            logger.info("사용 가능한 상담원 없음 — 대기열 추가: %s", session_id)
            self._enqueue(session_id, customer_id, tags=tags, is_vip=is_vip)
            return None
        agent = self._strategy.assign(available, customer_id, tags=tags, is_vip=is_vip)
        if agent:
            agent.current_sessions += 1
            logger.info("상담원 배정: 세션 %s → 상담원 %s", session_id, agent.agent_id)
        return agent

    def release(self, agent_id: str) -> Optional[AgentProfile]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        if agent.current_sessions > 0:
            agent.current_sessions -= 1
        return agent

    def get_wait_position(self, session_id: str) -> int:
        for i, entry in enumerate(self._queue):
            if entry.session_id == session_id:
                return i + 1
        return 0

    def dequeue_next(self) -> Optional[QueueEntry]:
        if not self._queue:
            return None
        return self._queue.pop(0)

    def get_queue(self) -> List[QueueEntry]:
        return list(self._queue)

    def get_stats(self) -> dict:
        agents = list(self._agents.values())
        available = [a for a in agents if a.is_available]
        return {
            'total_agents': len(agents),
            'available': len(available),
            'busy': len([a for a in agents if a.status == AgentStatus.busy]),
            'away': len([a for a in agents if a.status == AgentStatus.away]),
            'offline': len([a for a in agents if a.status == AgentStatus.offline]),
            'queue_length': len(self._queue),
            'total_current_sessions': sum(a.current_sessions for a in agents),
        }

    def get_agent_stats(self, agent_id: str) -> Optional[dict]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        return {
            'agent_id': agent.agent_id,
            'name': agent.name,
            'current_sessions': agent.current_sessions,
            'max_sessions': agent.max_sessions,
            'load_ratio': round(agent.load_ratio, 2),
            'rating': agent.rating,
            'status': agent.status.value if hasattr(agent.status, 'value') else agent.status,
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _enqueue(
        self,
        session_id: str,
        customer_id: str,
        tags: Optional[List[str]] = None,
        is_vip: bool = False,
    ) -> QueueEntry:
        entry = QueueEntry(
            session_id=session_id,
            customer_id=customer_id,
            priority=10 if is_vip else 0,
            tags=tags or [],
            is_vip=is_vip,
        )
        self._queue.append(entry)
        # 우선순위 높은 순서로 정렬
        self._queue.sort(key=lambda e: -e.priority)
        return entry
