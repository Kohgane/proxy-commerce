"""src/api/security_api.py — 보안 강화 API Blueprint (Phase 72)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

security_bp = Blueprint("security", __name__, url_prefix="/api/v1/security")


@security_bp.get("/audit")
def audit():
    """보안 감사 로그 조회."""
    from ..security.security_audit import SecurityAudit
    audit_obj = SecurityAudit()
    return jsonify(audit_obj.get_logs())


@security_bp.get("/sessions")
def sessions():
    """활성 세션 목록 조회."""
    from ..security.session_manager import SessionManager
    mgr = SessionManager()
    return jsonify(mgr.get_active_sessions())


@security_bp.get("/ip-filter")
def ip_filter():
    """IP 필터 목록 조회."""
    from ..security.ip_filter import IPFilter
    f = IPFilter()
    return jsonify(f.get_lists())


@security_bp.get("/policies")
def policies():
    """보안 정책 조회."""
    from ..security.security_manager import SecurityManager
    mgr = SecurityManager()
    return jsonify(mgr.get_security_status())


@security_bp.post("/ip-filter/block")
def ip_block():
    """IP 차단."""
    body = request.get_json(silent=True) or {}
    ip = body.get("ip", "")
    if not ip:
        return jsonify({"error": "ip 필드가 필요합니다"}), 400
    from ..security.ip_filter import IPFilter
    f = IPFilter()
    f.add_blacklist(ip)
    return jsonify({"ip": ip, "action": "blocked", "allowed": f.is_allowed(ip)})


@security_bp.post("/ip-filter/unblock")
def ip_unblock():
    """IP 차단 해제."""
    body = request.get_json(silent=True) or {}
    ip = body.get("ip", "")
    if not ip:
        return jsonify({"error": "ip 필드가 필요합니다"}), 400
    from ..security.ip_filter import IPFilter
    f = IPFilter()
    f.remove_blacklist(ip)
    return jsonify({"ip": ip, "action": "unblocked", "allowed": f.is_allowed(ip)})
