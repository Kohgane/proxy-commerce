"""src/api/security_advanced_api.py — 보안 강화 API Blueprint (Phase 116).

Blueprint: /api/v1/security
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

security_advanced_bp = Blueprint(
    'security_advanced',
    __name__,
    url_prefix='/api/v1/security',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_rbac_manager = None
_ip_manager = None
_request_signer = None
_audit_logger = None


def _get_rbac():
    global _rbac_manager
    if _rbac_manager is None:
        from src.security_advanced.rbac import RBACManager
        _rbac_manager = RBACManager()
    return _rbac_manager


def _get_ip_manager():
    global _ip_manager
    if _ip_manager is None:
        from src.security_advanced.ip_whitelist import IPWhitelistManager
        _ip_manager = IPWhitelistManager()
    return _ip_manager


def _get_signer():
    global _request_signer
    if _request_signer is None:
        from src.security_advanced.request_signer import RequestSigner
        _request_signer = RequestSigner()
    return _request_signer


def _get_audit():
    global _audit_logger
    if _audit_logger is None:
        from src.security_advanced.security_audit import SecurityAuditLogger
        _audit_logger = SecurityAuditLogger()
    return _audit_logger


def _to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for f in dataclasses.fields(obj):
            val = getattr(obj, f.name)
            if f.name in ("network",):  # ipaddress 객체 제외
                continue
            result[f.name] = _to_dict(val)
        return result
    if isinstance(obj, set):
        return sorted(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


# ════════════════════════════════════════════════════════════════════════════
# RBAC 엔드포인트
# ════════════════════════════════════════════════════════════════════════════

@security_advanced_bp.get("/roles")
def list_roles():
    """역할 목록."""
    rbac = _get_rbac()
    roles = rbac.list_roles()
    return jsonify({"roles": [_to_dict(r) for r in roles]}), 200


@security_advanced_bp.post("/roles")
def create_role():
    """역할 생성."""
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name", "")
    permissions = set(data.get("permissions", []))
    description = data.get("description", "")
    if not name:
        return jsonify({"error": "name 필수"}), 400
    rbac = _get_rbac()
    role = rbac.create_role(name, permissions, description)
    return jsonify({"role": _to_dict(role)}), 201


@security_advanced_bp.delete("/roles/<role_id>")
def delete_role(role_id: str):
    """역할 삭제 (내장 역할 불가)."""
    rbac = _get_rbac()
    try:
        rbac.delete_role(role_id)
        return jsonify({"deleted": role_id}), 200
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@security_advanced_bp.post("/roles/assign")
def assign_role():
    """사용자에게 역할 할당."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id", "")
    role_id = data.get("role_id", "")
    if not (user_id and role_id):
        return jsonify({"error": "user_id, role_id 필수"}), 400
    rbac = _get_rbac()
    try:
        rbac.assign_role(user_id, role_id)
        return jsonify({"assigned": {"user_id": user_id, "role_id": role_id}}), 200
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404


@security_advanced_bp.post("/roles/revoke")
def revoke_role():
    """사용자 역할 해제."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id", "")
    role_id = data.get("role_id", "")
    if not (user_id and role_id):
        return jsonify({"error": "user_id, role_id 필수"}), 400
    rbac = _get_rbac()
    rbac.revoke_role(user_id, role_id)
    return jsonify({"revoked": {"user_id": user_id, "role_id": role_id}}), 200


@security_advanced_bp.get("/users/<user_id>/permissions")
def get_user_permissions(user_id: str):
    """사용자 권한 조회."""
    rbac = _get_rbac()
    permissions = rbac.get_user_permissions(user_id)
    roles = rbac.get_user_roles(user_id)
    return jsonify({
        "user_id": user_id,
        "permissions": sorted(permissions),
        "roles": [_to_dict(r) for r in roles],
    }), 200


@security_advanced_bp.post("/check-permission")
def check_permission():
    """권한 확인."""
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id", "")
    permission = data.get("permission", "")
    if not (user_id and permission):
        return jsonify({"error": "user_id, permission 필수"}), 400
    rbac = _get_rbac()
    allowed = rbac.check_permission(user_id, permission)
    return jsonify({"user_id": user_id, "permission": permission, "allowed": allowed}), 200


# ════════════════════════════════════════════════════════════════════════════
# IP 화이트리스트 엔드포인트
# ════════════════════════════════════════════════════════════════════════════

@security_advanced_bp.get("/ip-whitelist")
def list_ip_whitelist():
    """등록된 IP 목록."""
    mgr = _get_ip_manager()
    return jsonify({"ips": [_to_dict(e) for e in mgr.list_ips()]}), 200


@security_advanced_bp.post("/ip-whitelist")
def add_ip():
    """IP/CIDR 추가."""
    data = request.get_json(force=True, silent=True) or {}
    ip_address = data.get("ip_address", "")
    description = data.get("description", "")
    added_by = data.get("added_by", "api")
    if not ip_address:
        return jsonify({"error": "ip_address 필수"}), 400
    mgr = _get_ip_manager()
    try:
        entry = mgr.add_ip(ip_address, description, added_by)
        return jsonify({"entry": _to_dict(entry)}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@security_advanced_bp.delete("/ip-whitelist/<path:ip_address>")
def remove_ip(ip_address: str):
    """IP/CIDR 삭제."""
    mgr = _get_ip_manager()
    try:
        mgr.remove_ip(ip_address)
        return jsonify({"deleted": ip_address}), 200
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404


@security_advanced_bp.get("/ip-whitelist/blocked")
def get_blocked_attempts():
    """차단 이력."""
    mgr = _get_ip_manager()
    attempts = mgr.get_blocked_attempts()
    return jsonify({"blocked": [_to_dict(a) for a in attempts]}), 200


# ════════════════════════════════════════════════════════════════════════════
# API 서명 엔드포인트
# ════════════════════════════════════════════════════════════════════════════

@security_advanced_bp.post("/api-keys")
def generate_api_key():
    """API 키 발급."""
    data = request.get_json(force=True, silent=True) or {}
    description = data.get("description", "")
    created_by = data.get("created_by", "api")
    signer = _get_signer()
    api_key, api_secret = signer.generate_api_key(description, created_by)
    return jsonify({"api_key": api_key, "api_secret": api_secret}), 201


@security_advanced_bp.get("/api-keys")
def list_api_keys():
    """API 키 목록 (secret 제외)."""
    signer = _get_signer()
    keys = signer.list_api_keys()
    return jsonify({"api_keys": [_to_dict(k) for k in keys]}), 200


@security_advanced_bp.delete("/api-keys/<api_key>")
def revoke_api_key(api_key: str):
    """API 키 비활성화."""
    signer = _get_signer()
    try:
        signer.revoke_api_key(api_key)
        return jsonify({"revoked": api_key}), 200
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404


@security_advanced_bp.post("/verify-signature")
def verify_signature():
    """서명 검증 테스트."""
    data = request.get_json(force=True, silent=True) or {}
    method = data.get("method", "GET")
    path = data.get("path", "/")
    body = data.get("body", "")
    timestamp = data.get("timestamp", "")
    signature = data.get("signature", "")
    api_key = data.get("api_key", "")
    if not (timestamp and signature and api_key):
        return jsonify({"error": "timestamp, signature, api_key 필수"}), 400
    signer = _get_signer()
    valid = signer.verify_signature(method, path, body, timestamp, signature, api_key)
    return jsonify({"valid": valid}), 200


# ════════════════════════════════════════════════════════════════════════════
# 보안 감사 엔드포인트
# ════════════════════════════════════════════════════════════════════════════

@security_advanced_bp.get("/audit-log")
def get_audit_log():
    """보안 이벤트 조회."""
    audit = _get_audit()
    filters = {}
    for key in ("event_type", "user_id", "result", "ip_address"):
        val = request.args.get(key)
        if val:
            filters[key] = val
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    result = audit.get_security_events(filters=filters, page=page, per_page=per_page)
    return jsonify(result), 200


@security_advanced_bp.get("/suspicious-activity")
def get_suspicious_activity():
    """의심 활동 조회."""
    audit = _get_audit()
    threshold = int(request.args.get("threshold", 10))
    window = int(request.args.get("window_minutes", 5))
    activities = audit.get_suspicious_activity(threshold=threshold, window_minutes=window)
    return jsonify({"suspicious": [_to_dict(a) for a in activities]}), 200
