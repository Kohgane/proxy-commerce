"""src/auth/api_key_manager.py — In-memory API key manager."""

import re
import secrets
from datetime import datetime, timedelta, timezone


class APIKeyManager:
    """Generate, validate, revoke, and list API keys (in-memory)."""

    _KEY_PATTERN = re.compile(r'^[a-z]+_[0-9a-f]{32}$')

    def __init__(self):
        self._keys: dict = {}  # key_id -> key record
        self._revoked: set = set()  # revoked key_ids

    def generate_key(self, prefix: str = 'pk', scopes: list = None, expires_in_days: int = 365) -> dict:
        """Generate a new API key."""
        raw = secrets.token_hex(16)
        key = f"{prefix}_{raw}"
        key_id = secrets.token_hex(8)
        now = datetime.now(tz=timezone.utc)
        expires_at = now + timedelta(days=expires_in_days)
        record = {
            'key': key,
            'prefix': prefix,
            'scopes': list(scopes) if scopes else [],
            'created_at': now.isoformat(),
            'expires_at': expires_at.isoformat(),
            'key_id': key_id,
        }
        self._keys[key_id] = record
        return dict(record)

    def validate_key(self, key: str) -> dict:
        """Validate a key by format and expiry. Returns validation result dict."""
        if not self._KEY_PATTERN.match(key):
            return {'valid': False, 'scopes': [], 'expired': False}

        for kid, record in self._keys.items():
            if record['key'] == key:
                if kid in self._revoked:
                    return {'valid': False, 'scopes': [], 'expired': False}
                expires_at = datetime.fromisoformat(record['expires_at'])
                expired = datetime.now(tz=timezone.utc) > expires_at
                return {
                    'valid': not expired,
                    'scopes': record['scopes'],
                    'expired': expired,
                }

        return {'valid': False, 'scopes': [], 'expired': False}

    def revoke_key(self, key_id: str) -> bool:
        """Revoke a key by its key_id. Returns True if found and revoked."""
        if key_id in self._keys:
            self._revoked.add(key_id)
            return True
        return False

    def list_keys(self) -> list:
        """Return list of non-revoked key records."""
        return [
            dict(record)
            for kid, record in self._keys.items()
            if kid not in self._revoked
        ]
