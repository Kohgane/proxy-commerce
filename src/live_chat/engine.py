"""src/live_chat/engine.py — 채팅 엔진 (Phase 107).

ChatEngine: 세션 생성 → 상담원 배정 → 메시지 교환 → 종료 → 만족도 조사
"""
from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ChatSessionStatus(str, Enum):
    waiting = 'waiting'
    assigned = 'assigned'
    active = 'active'
    on_hold = 'on_hold'
    resolved = 'resolved'
    closed = 'closed'


class MessageType(str, Enum):
    text = 'text'
    image = 'image'
    file = 'file'
    system = 'system'
    auto_reply = 'auto_reply'
    quick_reply = 'quick_reply'


class SenderType(str, Enum):
    customer = 'customer'
    agent = 'agent'
    bot = 'bot'
    system = 'system'


@dataclass
class ChatMessage:
    message_id: str
    session_id: str
    sender_type: SenderType
    sender_id: str
    content: str
    message_type: MessageType = MessageType.text
    timestamp: str = ''
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'message_id': self.message_id,
            'session_id': self.session_id,
            'sender_type': self.sender_type.value if hasattr(self.sender_type, 'value') else self.sender_type,
            'sender_id': self.sender_id,
            'content': self.content,
            'message_type': self.message_type.value if hasattr(self.message_type, 'value') else self.message_type,
            'timestamp': self.timestamp,
            'metadata': self.metadata,
        }


@dataclass
class ChatSession:
    session_id: str
    customer_id: str
    agent_id: Optional[str] = None
    status: ChatSessionStatus = ChatSessionStatus.waiting
    channel: str = 'web'
    started_at: str = ''
    ended_at: Optional[str] = None
    messages: List[ChatMessage] = field(default_factory=list)
    rating: Optional[int] = None
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'customer_id': self.customer_id,
            'agent_id': self.agent_id,
            'status': self.status.value if hasattr(self.status, 'value') else self.status,
            'channel': self.channel,
            'started_at': self.started_at,
            'ended_at': self.ended_at,
            'message_count': len(self.messages),
            'rating': self.rating,
            'tags': self.tags,
        }


class ChatEngine:
    """채팅 엔진 — 세션 생성/관리/메시지 교환/종료/만족도 조사 오케스트레이션."""

    def __init__(self):
        self._sessions: Dict[str, ChatSession] = {}

    # ── 세션 관리 ────────────────────────────────────────────────────────────

    def create_session(
        self,
        customer_id: str,
        channel: str = 'web',
        tags: Optional[List[str]] = None,
    ) -> ChatSession:
        session_id = str(uuid.uuid4())
        session = ChatSession(
            session_id=session_id,
            customer_id=customer_id,
            channel=channel,
            tags=tags or [],
        )
        self._sessions[session_id] = session
        # 시스템 메시지 추가
        self._add_system_message(session, '채팅 세션이 시작되었습니다.')
        logger.info("채팅 세션 생성: %s (고객: %s)", session_id, customer_id)
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        return self._sessions.get(session_id)

    def list_sessions(
        self,
        status: Optional[ChatSessionStatus] = None,
        customer_id: Optional[str] = None,
    ) -> List[ChatSession]:
        sessions = list(self._sessions.values())
        if status:
            sessions = [s for s in sessions if s.status == status]
        if customer_id:
            sessions = [s for s in sessions if s.customer_id == customer_id]
        return sessions

    def assign_agent(self, session_id: str, agent_id: str) -> Optional[ChatSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.agent_id = agent_id
        session.status = ChatSessionStatus.assigned
        self._add_system_message(session, f'상담원이 배정되었습니다.')
        logger.info("상담원 배정: 세션 %s → 상담원 %s", session_id, agent_id)
        return session

    def activate_session(self, session_id: str) -> Optional[ChatSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.status = ChatSessionStatus.active
        return session

    def hold_session(self, session_id: str) -> Optional[ChatSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.status = ChatSessionStatus.on_hold
        self._add_system_message(session, '상담이 잠시 보류되었습니다.')
        return session

    def close_session(self, session_id: str, resolution: str = '') -> Optional[ChatSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.status = ChatSessionStatus.closed
        session.ended_at = datetime.now(tz=timezone.utc).isoformat()
        msg = '채팅 세션이 종료되었습니다.'
        if resolution:
            msg += f' ({resolution})'
        self._add_system_message(session, msg)
        logger.info("채팅 세션 종료: %s", session_id)
        return session

    def resolve_session(self, session_id: str) -> Optional[ChatSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.status = ChatSessionStatus.resolved
        self._add_system_message(session, '문의가 해결되었습니다.')
        return session

    def rate_session(self, session_id: str, rating: int) -> Optional[ChatSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        if not (1 <= rating <= 5):
            raise ValueError('rating must be 1-5')
        session.rating = rating
        logger.info("만족도 평가: 세션 %s = %d", session_id, rating)
        return session

    # ── 메시지 관리 ────────────────────────────────────────────────────────────

    def send_message(
        self,
        session_id: str,
        sender_type: SenderType,
        sender_id: str,
        content: str,
        message_type: MessageType = MessageType.text,
        metadata: Optional[Dict] = None,
    ) -> Optional[ChatMessage]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        if session.status in (ChatSessionStatus.closed, ChatSessionStatus.resolved):
            return None
        msg = ChatMessage(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            metadata=metadata or {},
        )
        session.messages.append(msg)
        # 첫 메시지 교환 시 active로 전환
        if session.status == ChatSessionStatus.assigned:
            session.status = ChatSessionStatus.active
        return msg

    def get_messages(self, session_id: str) -> List[ChatMessage]:
        session = self._sessions.get(session_id)
        if not session:
            return []
        return list(session.messages)

    def transfer_session(self, session_id: str, new_agent_id: str) -> Optional[ChatSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        old_agent = session.agent_id
        session.agent_id = new_agent_id
        session.status = ChatSessionStatus.assigned
        self._add_system_message(
            session,
            f'상담원이 변경되었습니다. ({old_agent} → {new_agent_id})',
        )
        logger.info("세션 이관: %s → 상담원 %s", session_id, new_agent_id)
        return session

    # ── 통계 ──────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        sessions = list(self._sessions.values())
        total = len(sessions)
        by_status: Dict[str, int] = {}
        for s in sessions:
            key = s.status.value if hasattr(s.status, 'value') else str(s.status)
            by_status[key] = by_status.get(key, 0) + 1
        rated = [s for s in sessions if s.rating is not None]
        avg_rating = (sum(s.rating for s in rated) / len(rated)) if rated else 0.0
        return {
            'total_sessions': total,
            'by_status': by_status,
            'average_rating': round(avg_rating, 2),
            'rated_sessions': len(rated),
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _add_system_message(self, session: ChatSession, content: str) -> ChatMessage:
        msg = ChatMessage(
            message_id=str(uuid.uuid4()),
            session_id=session.session_id,
            sender_type=SenderType.system,
            sender_id='system',
            content=content,
            message_type=MessageType.system,
        )
        session.messages.append(msg)
        return msg
