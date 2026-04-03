"""src/realtime/connection_manager.py — 연결 관리자."""
from __future__ import annotations

import datetime
import uuid


class ConnectionManager:
    """WebSocket/SSE 연결 관리자."""

    def __init__(self) -> None:
        self._connections: dict[str, dict] = {}

    def connect(self, client_id: str) -> dict:
        """클라이언트를 연결한다."""
        connection = {
            "client_id": client_id,
            "connection_id": str(uuid.uuid4()),
            "connected_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "last_heartbeat": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "status": "connected",
        }
        self._connections[client_id] = connection
        return connection

    def disconnect(self, client_id: str) -> bool:
        """클라이언트를 연결 해제한다."""
        if client_id in self._connections:
            del self._connections[client_id]
            return True
        return False

    def heartbeat(self, client_id: str) -> bool:
        """클라이언트 하트비트를 갱신한다."""
        if client_id in self._connections:
            self._connections[client_id]["last_heartbeat"] = (
                datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
            )
            return True
        return False

    def get_connections(self) -> list:
        """모든 연결 목록을 반환한다."""
        return list(self._connections.values())

    def get_stats(self) -> dict:
        """연결 통계를 반환한다."""
        total = len(self._connections)
        return {
            "total_connections": total,
            "active_channels": total,
            "heartbeat_rate": 1.0 if total > 0 else 0.0,
        }
