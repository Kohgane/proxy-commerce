"""src/auth/jwt_handler.py — Pure-Python JWT handler (HMAC-SHA256, no external jwt library)."""

import base64
import hashlib
import hmac
import json
import os
import time


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += '=' * padding
    return base64.urlsafe_b64decode(s)


class JWTHandler:
    """Simple JWT handler using HMAC-SHA256."""

    def __init__(self, secret_key: str = None, algorithm: str = 'HS256'):
        self.secret_key = secret_key or os.getenv('JWT_SECRET_KEY', 'dev-secret-key')
        self.algorithm = algorithm

    def _sign(self, header_b64: str, payload_b64: str) -> str:
        message = f"{header_b64}.{payload_b64}".encode('utf-8')
        sig = hmac.new(self.secret_key.encode('utf-8'), message, hashlib.sha256).digest()
        return _b64url_encode(sig)

    def _build_token(self, payload: dict) -> str:
        header = {"alg": self.algorithm, "typ": "JWT"}
        header_b64 = _b64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
        signature = self._sign(header_b64, payload_b64)
        return f"{header_b64}.{payload_b64}.{signature}"

    def create_access_token(self, payload: dict, expires_in_minutes: int = 15) -> str:
        """Create a JWT access token with expiry."""
        data = dict(payload)
        data['exp'] = int(time.time()) + expires_in_minutes * 60
        data['iat'] = int(time.time())
        data['type'] = 'access'
        return self._build_token(data)

    def create_refresh_token(self, payload: dict, expires_in_days: int = 7) -> str:
        """Create a JWT refresh token with expiry."""
        data = dict(payload)
        data['exp'] = int(time.time()) + expires_in_days * 86400
        data['iat'] = int(time.time())
        data['type'] = 'refresh'
        return self._build_token(data)

    def decode_token(self, token: str) -> dict:
        """Decode and validate a JWT token. Raises ValueError if invalid or expired."""
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid token format")

        header_b64, payload_b64, signature = parts

        expected_sig = self._sign(header_b64, payload_b64)
        if not hmac.compare_digest(expected_sig, signature):
            raise ValueError("Invalid token signature")

        try:
            payload = json.loads(_b64url_decode(payload_b64))
        except Exception:
            raise ValueError("Invalid token payload")

        exp = payload.get('exp')
        if exp is not None and int(time.time()) > exp:
            raise ValueError("Token has expired")

        return payload

    def is_token_expired(self, token: str) -> bool:
        """Return True if the token is expired or invalid."""
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return True
            payload = json.loads(_b64url_decode(parts[1]))
            exp = payload.get('exp')
            if exp is None:
                return False
            return int(time.time()) > exp
        except Exception:
            return True
