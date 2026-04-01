"""src/middleware/auth_middleware.py — JWT and API key decorators for Flask routes."""

import functools
import logging

from flask import g, request, jsonify

from ..auth.jwt_handler import JWTHandler
from ..auth.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

_jwt_handler = JWTHandler()
_api_key_manager = APIKeyManager()


def require_jwt(f):
    """Decorator: requires valid Bearer JWT in Authorization header."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Unauthorized', 'message': 'Missing or invalid Authorization header'}), 401
        token = auth_header[len('Bearer '):]
        try:
            payload = _jwt_handler.decode_token(token)
            g.jwt_payload = payload
        except ValueError as exc:
            logger.warning("JWT validation failed: %s", exc)
            return jsonify({'error': 'Unauthorized', 'message': 'Invalid or expired token'}), 401
        return f(*args, **kwargs)
    return wrapper


def require_api_key(f):
    """Decorator: requires valid X-API-Key header."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        key = request.headers.get('X-API-Key', '')
        if not key:
            return jsonify({'error': 'Unauthorized', 'message': 'Missing X-API-Key header'}), 401
        result = _api_key_manager.validate_key(key)
        if not result['valid']:
            return jsonify({'error': 'Unauthorized', 'message': 'Invalid or expired API key'}), 401
        return f(*args, **kwargs)
    return wrapper
