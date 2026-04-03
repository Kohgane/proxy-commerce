"""src/security/security_manager.py — 보안 관리자."""
from __future__ import annotations

from .input_sanitizer import InputSanitizer
from .csrf_protection import CSRFProtection
from .content_security_policy import ContentSecurityPolicy
from .security_headers import SecurityHeaders
from .ip_filter import IPFilter
from .security_audit import SecurityAudit
from .password_policy import PasswordPolicy
from .session_manager import SessionManager


class SecurityManager:
    """보안 컴포넌트 오케스트레이터."""

    def __init__(self) -> None:
        self.sanitizer = InputSanitizer()
        self.csrf = CSRFProtection()
        self.csp = ContentSecurityPolicy()
        self.headers = SecurityHeaders()
        self.ip_filter = IPFilter()
        self.audit = SecurityAudit()
        self.password_policy = PasswordPolicy()
        self.session_manager = SessionManager()

    def check_request(self, ip: str, session_id: str | None = None) -> dict:
        """요청의 보안 상태를 확인한다."""
        allowed = self.ip_filter.is_allowed(ip)
        session_valid = False
        if session_id:
            session = self.session_manager.get_session(session_id)
            session_valid = bool(session)
        return {
            "ip": ip,
            "ip_allowed": allowed,
            "session_valid": session_valid,
            "headers": self.headers.get_headers(),
            "csp": self.csp.generate_header(),
        }

    def get_security_status(self) -> dict:
        """보안 전반 상태를 반환한다."""
        return {
            "active_sessions": len(self.session_manager.get_active_sessions()),
            "ip_filter": self.ip_filter.get_lists(),
            "csp_enabled": True,
            "security_headers": list(self.headers.get_headers().keys()),
            "audit_logs": len(self.audit.get_logs()),
            "suspicious_activity": self.audit.get_suspicious_activity(),
        }
