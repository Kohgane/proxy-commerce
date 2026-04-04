"""src/mobile_api/mobile_auth.py — 모바일 인증 관리자."""
from __future__ import annotations

import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    device_id: str
    platform: str  # ios / android / web
    push_token: str = ''
    app_version: str = '1.0.0'
    os_version: str = ''
    model: str = ''


@dataclass
class MobileSession:
    session_id: str
    user_id: str
    device_id: str
    access_token: str
    refresh_token: str
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    expires_at: float = 0.0


class MobileAuthManager:
    """모바일 전용 JWT 인증 관리자."""

    MAX_SESSIONS = 5

    def __init__(self):
        self._devices: dict[str, DeviceInfo] = {}
        self._sessions: dict[str, MobileSession] = {}
        self._user_sessions: dict[str, list[str]] = {}
        from ..auth.jwt_handler import JWTHandler
        self._jwt = JWTHandler()
        # simple in-memory user store for demo
        self._users: dict[str, dict] = {
            'user_001': {'email': 'user@example.com', 'password': 'pass123', 'name': 'Test User'},
        }

    def login(self, email: str, password: str, device_info: DeviceInfo) -> dict:
        """로그인 → access_token (1h) + refresh_token (30d) 반환."""
        user = None
        user_id = None
        for uid, u in self._users.items():
            if u['email'] == email and u['password'] == password:
                user = u
                user_id = uid
                break
        if not user:
            raise ValueError('Invalid credentials')

        payload = {'sub': user_id, 'email': email}
        access_token = self._jwt.create_access_token(payload, expires_in_minutes=60)
        refresh_token = self._jwt.create_refresh_token(payload, expires_in_days=30)

        session_id = str(uuid.uuid4())
        now = time.time()
        session = MobileSession(
            session_id=session_id,
            user_id=user_id,
            device_id=device_info.device_id,
            access_token=access_token,
            refresh_token=refresh_token,
            created_at=now,
            last_active=now,
            expires_at=now + 30 * 86400,
        )
        self._sessions[session_id] = session

        sessions = self._user_sessions.setdefault(user_id, [])
        sessions.append(session_id)
        # Enforce max 5 sessions: remove oldest
        while len(sessions) > self.MAX_SESSIONS:
            old_id = sessions.pop(0)
            self._sessions.pop(old_id, None)

        self.register_device(user_id, device_info)

        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'session_id': session_id,
            'user_id': user_id,
            'expires_in': 3600,
        }

    def refresh_token(self, refresh_token_str: str, device_id: str) -> dict:
        """Refresh → new access_token."""
        try:
            payload = self._jwt.decode_token(refresh_token_str)
        except ValueError as exc:
            raise ValueError(f'Invalid refresh token: {exc}') from exc
        if payload.get('type') != 'refresh':
            raise ValueError('Token is not a refresh token')
        user_id = payload.get('sub', '')
        new_payload = {'sub': user_id, 'email': payload.get('email', '')}
        access_token = self._jwt.create_access_token(new_payload, expires_in_minutes=60)
        # update session
        for sid in self._user_sessions.get(user_id, []):
            s = self._sessions.get(sid)
            if s and s.device_id == device_id:
                s.access_token = access_token
                s.last_active = time.time()
                break
        return {'access_token': access_token, 'expires_in': 3600}

    def register_device(self, user_id: str, device_info: DeviceInfo) -> bool:
        self._devices[device_info.device_id] = device_info
        return True

    def logout(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session:
            sessions = self._user_sessions.get(session.user_id, [])
            if session_id in sessions:
                sessions.remove(session_id)
        return session is not None

    def get_active_sessions(self, user_id: str) -> list[dict]:
        result = []
        for sid in self._user_sessions.get(user_id, []):
            s = self._sessions.get(sid)
            if s:
                result.append({
                    'session_id': s.session_id,
                    'device_id': s.device_id,
                    'created_at': s.created_at,
                    'last_active': s.last_active,
                })
        return result

    def validate_token(self, token: str) -> dict:
        try:
            return self._jwt.decode_token(token)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
