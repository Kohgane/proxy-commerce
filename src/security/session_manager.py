"""src/security/session_manager.py — 세션 관리자."""
from __future__ import annotations

import datetime
import secrets
import uuid

_MAX_SESSIONS_PER_USER = 5


class SessionManager:
    """세션 관리자."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    def create_session(self, user_id: str) -> dict:
        """새 세션을 생성한다. 최대 5개 초과 시 가장 오래된 세션을 제거한다."""
        user_sessions = [s for s in self._sessions.values() if s["user_id"] == user_id]
        if len(user_sessions) >= _MAX_SESSIONS_PER_USER:
            oldest = sorted(user_sessions, key=lambda s: s["created_at"])[0]
            del self._sessions[oldest["session_id"]]

        session_id = str(uuid.uuid4())
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "token": secrets.token_hex(32),
            "created_at": now.isoformat(),
            "expires_at": (now + datetime.timedelta(hours=24)).isoformat(),
            "active": True,
        }
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> dict:
        """세션을 반환한다."""
        return self._sessions.get(session_id, {})

    def expire_session(self, session_id: str) -> bool:
        """세션을 만료시킨다."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def force_logout(self, user_id: str) -> int:
        """사용자의 모든 세션을 강제 종료한다."""
        to_remove = [sid for sid, s in self._sessions.items() if s["user_id"] == user_id]
        for sid in to_remove:
            del self._sessions[sid]
        return len(to_remove)

    def get_active_sessions(self) -> list:
        """활성 세션 목록을 반환한다."""
        return list(self._sessions.values())

    def cleanup_expired(self) -> int:
        """만료된 세션을 정리한다."""
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        to_remove = []
        for sid, session in self._sessions.items():
            expires_at = datetime.datetime.fromisoformat(session["expires_at"])
            if now > expires_at:
                to_remove.append(sid)
        for sid in to_remove:
            del self._sessions[sid]
        return len(to_remove)
