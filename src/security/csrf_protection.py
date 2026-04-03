"""src/security/csrf_protection.py — CSRF 보호."""
from __future__ import annotations

import hashlib
import secrets


class CSRFProtection:
    """CSRF 보호."""

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}

    def generate_token(self, session_id: str) -> str:
        """세션에 대한 CSRF 토큰을 생성한다."""
        raw = secrets.token_hex(32)
        token = hashlib.sha256(f"{session_id}:{raw}".encode()).hexdigest()
        self._tokens[session_id] = token
        return token

    def validate_token(self, session_id: str, token: str) -> bool:
        """CSRF 토큰을 검증한다."""
        expected = self._tokens.get(session_id)
        if not expected:
            return False
        return secrets.compare_digest(expected, token)

    def invalidate(self, session_id: str) -> None:
        """세션의 CSRF 토큰을 무효화한다."""
        self._tokens.pop(session_id, None)
