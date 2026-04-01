"""src/api/auth_api.py — Auth API Blueprint (JWT login, token refresh, API key management)."""

import logging

from flask import Blueprint, request, jsonify

from ..auth.jwt_handler import JWTHandler
from ..auth.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

auth_api_bp = Blueprint('auth_api', __name__, url_prefix='/api/v1/auth')

_jwt = JWTHandler()
_key_manager = APIKeyManager()


@auth_api_bp.route('/login', methods=['POST'])
def login():
    """Demo login: accepts any credentials and returns JWT tokens.

    WARNING: This is a demo implementation only. Do NOT deploy to production
    without adding real credential validation (e.g., database user lookup + password hashing).
    """
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')  # noqa: F841 — demo mode: password not validated

    if not username:
        return jsonify({'error': 'username is required'}), 400

    payload = {'sub': username, 'username': username}
    access_token = _jwt.create_access_token(payload)
    refresh_token = _jwt.create_refresh_token(payload)

    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'Bearer',
    }), 200


@auth_api_bp.route('/token/refresh', methods=['GET'])
def refresh_token():
    """Refresh access token using a refresh token from Authorization header."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing refresh token'}), 400

    token = auth_header[len('Bearer '):]
    try:
        payload = _jwt.decode_token(token)
    except ValueError:
        return jsonify({'error': 'Invalid or expired token'}), 401

    if payload.get('type') != 'refresh':
        return jsonify({'error': 'Not a refresh token'}), 400

    new_payload = {k: v for k, v in payload.items() if k not in ('exp', 'iat', 'type')}
    access_token = _jwt.create_access_token(new_payload)
    return jsonify({'access_token': access_token, 'token_type': 'Bearer'}), 200


@auth_api_bp.route('/api-keys', methods=['GET'])
def list_api_keys():
    """List all non-revoked API keys."""
    return jsonify({'keys': _key_manager.list_keys()}), 200


@auth_api_bp.route('/api-keys', methods=['POST'])
def create_api_key():
    """Generate a new API key."""
    data = request.get_json(silent=True) or {}
    prefix = data.get('prefix', 'pk')
    scopes = data.get('scopes', [])
    expires_in_days = data.get('expires_in_days', 365)
    record = _key_manager.generate_key(prefix=prefix, scopes=scopes, expires_in_days=expires_in_days)
    return jsonify(record), 201


@auth_api_bp.route('/api-keys/<key_id>', methods=['DELETE'])
def revoke_api_key(key_id: str):
    """Revoke an API key by key_id."""
    success = _key_manager.revoke_key(key_id)
    if success:
        return jsonify({'revoked': True, 'key_id': key_id}), 200
    return jsonify({'error': 'Key not found', 'key_id': key_id}), 404
