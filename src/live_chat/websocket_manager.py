"""src/live_chat/websocket_manager.py — WebSocket 관리 (Phase 107, mock 시뮬레이션)."""
from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Connection:
    connection_id: str
    user_id: str
    user_type: str  # 'customer' | 'agent' | 'system'
    connected_at: str = ''
    last_ping: str = ''
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        now = datetime.now(tz=timezone.utc).isoformat()
        if not self.connected_at:
            self.connected_at = now
        if not self.last_ping:
            self.last_ping = now

    def to_dict(self) -> dict:
        return {
            'connection_id': self.connection_id,
            'user_id': self.user_id,
            'user_type': self.user_type,
            'connected_at': self.connected_at,
            'last_ping': self.last_ping,
            'metadata': self.metadata,
        }


class WebSocketManager:
    """WebSocket 연결 관리 (mock 시뮬레이션)."""

    def __init__(self):
        self._connections: Dict[str, Connection] = {}  # connection_id → Connection
        self._user_connections: Dict[str, List[str]] = {}  # user_id → [connection_id]
        self._messages: List[dict] = []  # 브로드캐스트/유니캐스트 기록

    # ── 연결 관리 ────────────────────────────────────────────────────────────

    def connect(self, user_id: str, user_type: str, metadata: Optional[Dict] = None) -> Connection:
        connection_id = str(uuid.uuid4())
        conn = Connection(
            connection_id=connection_id,
            user_id=user_id,
            user_type=user_type,
            metadata=metadata or {},
        )
        self._connections[connection_id] = conn
        if user_id not in self._user_connections:
            self._user_connections[user_id] = []
        self._user_connections[user_id].append(connection_id)
        logger.info("WebSocket 연결: %s (사용자: %s, 유형: %s)", connection_id, user_id, user_type)
        return conn

    def disconnect(self, connection_id: str) -> bool:
        conn = self._connections.pop(connection_id, None)
        if not conn:
            return False
        uid = conn.user_id
        if uid in self._user_connections:
            self._user_connections[uid] = [
                cid for cid in self._user_connections[uid] if cid != connection_id
            ]
            if not self._user_connections[uid]:
                del self._user_connections[uid]
        logger.info("WebSocket 해제: %s (사용자: %s)", connection_id, uid)
        return True

    def reconnect(self, user_id: str, user_type: str, metadata: Optional[Dict] = None) -> Connection:
        # 기존 연결 모두 해제
        for cid in list(self._user_connections.get(user_id, [])):
            self.disconnect(cid)
        return self.connect(user_id, user_type, metadata)

    def get_connection(self, connection_id: str) -> Optional[Connection]:
        return self._connections.get(connection_id)

    def get_user_connections(self, user_id: str) -> List[Connection]:
        return [
            self._connections[cid]
            for cid in self._user_connections.get(user_id, [])
            if cid in self._connections
        ]

    # ── 하트비트 ─────────────────────────────────────────────────────────────

    def ping(self, connection_id: str) -> bool:
        conn = self._connections.get(connection_id)
        if not conn:
            return False
        conn.last_ping = datetime.now(tz=timezone.utc).isoformat()
        return True

    def check_heartbeat(self, timeout_seconds: int = 60) -> List[str]:
        """타임아웃된 연결 목록 반환 (mock: 항상 빈 리스트)."""
        return []

    # ── 메시지 전송 ───────────────────────────────────────────────────────────

    def broadcast(self, event: str, data: dict, user_type: Optional[str] = None) -> int:
        """특정 유형(또는 전체) 사용자에게 브로드캐스트."""
        count = 0
        for conn in self._connections.values():
            if user_type and conn.user_type != user_type:
                continue
            record = {
                'type': 'broadcast',
                'event': event,
                'data': data,
                'target_connection': conn.connection_id,
                'sent_at': datetime.now(tz=timezone.utc).isoformat(),
            }
            self._messages.append(record)
            count += 1
        logger.debug("브로드캐스트: %s → %d명", event, count)
        return count

    def unicast(self, user_id: str, event: str, data: dict) -> bool:
        """특정 사용자에게 유니캐스트."""
        connections = self.get_user_connections(user_id)
        if not connections:
            return False
        for conn in connections:
            record = {
                'type': 'unicast',
                'event': event,
                'data': data,
                'target_user': user_id,
                'target_connection': conn.connection_id,
                'sent_at': datetime.now(tz=timezone.utc).isoformat(),
            }
            self._messages.append(record)
        logger.debug("유니캐스트: %s → 사용자 %s", event, user_id)
        return True

    # ── 상태 모니터링 ─────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        total = len(self._connections)
        by_type: Dict[str, int] = {}
        for conn in self._connections.values():
            by_type[conn.user_type] = by_type.get(conn.user_type, 0) + 1
        return {
            'total_connections': total,
            'by_type': by_type,
            'online_customers': by_type.get('customer', 0),
            'online_agents': by_type.get('agent', 0),
            'messages_sent': len(self._messages),
        }

    def get_message_log(self) -> List[dict]:
        return list(self._messages)
