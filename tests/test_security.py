"""tests/test_security.py — Phase 72 보안 강화 테스트."""
from __future__ import annotations

import pytest
from src.security.input_sanitizer import InputSanitizer
from src.security.csrf_protection import CSRFProtection
from src.security.content_security_policy import ContentSecurityPolicy
from src.security.security_headers import SecurityHeaders
from src.security.ip_filter import IPFilter
from src.security.security_audit import SecurityAudit
from src.security.password_policy import PasswordPolicy
from src.security.session_manager import SessionManager
from src.security.security_manager import SecurityManager


class TestInputSanitizer:
    def test_sanitize_xss_script_tag(self):
        s = InputSanitizer()
        result = s.sanitize_xss("<script>alert('xss')</script>")
        assert "<script>" not in result

    def test_sanitize_xss_clean_text(self):
        s = InputSanitizer()
        text = "안녕하세요 일반 텍스트"
        assert s.sanitize_xss(text) == text

    def test_sanitize_sql(self):
        s = InputSanitizer()
        result = s.sanitize_sql("SELECT * FROM users --")
        assert "SELECT" not in result or "--" not in result

    def test_sanitize_path(self):
        s = InputSanitizer()
        result = s.sanitize_path("../../etc/passwd")
        assert "../" not in result

    def test_sanitize_all(self):
        s = InputSanitizer()
        evil = "<script>alert(1)</script> OR 1=1 --"
        result = s.sanitize_all(evil)
        assert "<script>" not in result


class TestCSRFProtection:
    def test_generate_and_validate_token(self):
        csrf = CSRFProtection()
        token = csrf.generate_token("session1")
        assert csrf.validate_token("session1", token) is True

    def test_invalid_token(self):
        csrf = CSRFProtection()
        csrf.generate_token("session1")
        assert csrf.validate_token("session1", "wrong_token") is False

    def test_no_token_for_session(self):
        csrf = CSRFProtection()
        assert csrf.validate_token("unknown", "token") is False

    def test_invalidate(self):
        csrf = CSRFProtection()
        token = csrf.generate_token("session1")
        csrf.invalidate("session1")
        assert csrf.validate_token("session1", token) is False


class TestContentSecurityPolicy:
    def test_generate_header(self):
        csp = ContentSecurityPolicy()
        header = csp.generate_header()
        assert "default-src" in header
        assert "'self'" in header

    def test_add_directive(self):
        csp = ContentSecurityPolicy()
        csp.add_directive("script-src", "https://cdn.example.com")
        header = csp.generate_header()
        assert "https://cdn.example.com" in header

    def test_get_policy(self):
        csp = ContentSecurityPolicy()
        policy = csp.get_policy()
        assert isinstance(policy, dict)
        assert "default-src" in policy


class TestSecurityHeaders:
    def test_get_headers(self):
        sh = SecurityHeaders()
        headers = sh.get_headers()
        assert "X-Frame-Options" in headers
        assert "X-Content-Type-Options" in headers
        assert "Strict-Transport-Security" in headers
        assert "Referrer-Policy" in headers
        assert "X-XSS-Protection" in headers


class TestIPFilter:
    def test_allow_by_default(self):
        f = IPFilter()
        assert f.is_allowed("192.168.1.1") is True

    def test_blacklist_blocks(self):
        f = IPFilter()
        f.add_blacklist("10.0.0.1")
        assert f.is_allowed("10.0.0.1") is False

    def test_whitelist_allows(self):
        f = IPFilter()
        f.add_whitelist("192.168.1.1")
        assert f.is_allowed("192.168.1.1") is True
        assert f.is_allowed("10.0.0.1") is False

    def test_remove_blacklist(self):
        f = IPFilter()
        f.add_blacklist("10.0.0.1")
        f.remove_blacklist("10.0.0.1")
        assert f.is_allowed("10.0.0.1") is True

    def test_cidr_blacklist(self):
        f = IPFilter()
        f.add_blacklist("192.168.0.0/24")
        assert f.is_allowed("192.168.0.50") is False
        assert f.is_allowed("10.0.0.1") is True

    def test_get_lists(self):
        f = IPFilter()
        f.add_whitelist("1.2.3.4")
        f.add_blacklist("5.6.7.8")
        lists = f.get_lists()
        assert "1.2.3.4" in lists["whitelist"]
        assert "5.6.7.8" in lists["blacklist"]


class TestSecurityAudit:
    def test_log_event(self):
        audit = SecurityAudit()
        entry = audit.log_event("login_success", "user1", "1.2.3.4")
        assert entry["event_type"] == "login_success"
        assert entry["user_id"] == "user1"

    def test_get_logs(self):
        audit = SecurityAudit()
        audit.log_event("login_success", "u1", "1.1.1.1")
        audit.log_event("login_failed", "u2", "2.2.2.2")
        assert len(audit.get_logs()) == 2

    def test_get_logs_filter(self):
        audit = SecurityAudit()
        audit.log_event("login_success", "u1", "1.1.1.1")
        audit.log_event("login_failed", "u2", "2.2.2.2")
        failed = audit.get_logs(event_type="login_failed")
        assert len(failed) == 1

    def test_get_suspicious_activity(self):
        audit = SecurityAudit()
        for _ in range(6):
            audit.log_event("login_failed", "attacker", "9.9.9.9")
        suspicious = audit.get_suspicious_activity()
        assert len(suspicious) == 1
        assert suspicious[0]["ip"] == "9.9.9.9"

    def test_no_suspicious_activity(self):
        audit = SecurityAudit()
        for _ in range(3):
            audit.log_event("login_failed", "user", "1.1.1.1")
        assert audit.get_suspicious_activity() == []


class TestPasswordPolicy:
    def test_valid_password(self):
        policy = PasswordPolicy()
        result = policy.validate("StrongPass1!")
        assert result["valid"] is True
        assert result["errors"] == []

    def test_too_short(self):
        policy = PasswordPolicy()
        result = policy.validate("Ab1!")
        assert result["valid"] is False
        assert any("자" in e for e in result["errors"])

    def test_no_uppercase(self):
        policy = PasswordPolicy()
        result = policy.validate("weakpass1!")
        assert result["valid"] is False

    def test_no_number(self):
        policy = PasswordPolicy()
        result = policy.validate("NoNumbers!")
        assert result["valid"] is False

    def test_no_special(self):
        policy = PasswordPolicy()
        result = policy.validate("NoSpecial1")
        assert result["valid"] is False

    def test_check_history(self):
        policy = PasswordPolicy()
        h = "hashvalue123"
        assert policy.check_history("user1", h) is False
        assert policy.check_history("user1", h) is True


class TestSessionManager:
    def test_create_session(self):
        mgr = SessionManager()
        session = mgr.create_session("user1")
        assert session["user_id"] == "user1"
        assert "session_id" in session
        assert "token" in session

    def test_get_session(self):
        mgr = SessionManager()
        session = mgr.create_session("user1")
        fetched = mgr.get_session(session["session_id"])
        assert fetched["user_id"] == "user1"

    def test_expire_session(self):
        mgr = SessionManager()
        session = mgr.create_session("user1")
        assert mgr.expire_session(session["session_id"]) is True
        assert mgr.get_session(session["session_id"]) == {}

    def test_force_logout(self):
        mgr = SessionManager()
        mgr.create_session("user1")
        mgr.create_session("user1")
        count = mgr.force_logout("user1")
        assert count == 2
        assert mgr.get_active_sessions() == []

    def test_max_concurrent_sessions(self):
        mgr = SessionManager()
        sessions = [mgr.create_session("user1") for _ in range(6)]
        assert len(mgr.get_active_sessions()) <= 5

    def test_get_active_sessions(self):
        mgr = SessionManager()
        mgr.create_session("u1")
        mgr.create_session("u2")
        assert len(mgr.get_active_sessions()) == 2

    def test_cleanup_expired(self):
        mgr = SessionManager()
        mgr.create_session("user1")
        count = mgr.cleanup_expired()
        assert count == 0


class TestSecurityManager:
    def test_check_request_allowed_ip(self):
        mgr = SecurityManager()
        result = mgr.check_request("192.168.1.1")
        assert result["ip_allowed"] is True

    def test_check_request_blocked_ip(self):
        mgr = SecurityManager()
        mgr.ip_filter.add_blacklist("10.0.0.1")
        result = mgr.check_request("10.0.0.1")
        assert result["ip_allowed"] is False

    def test_get_security_status(self):
        mgr = SecurityManager()
        status = mgr.get_security_status()
        assert "active_sessions" in status
        assert "ip_filter" in status
        assert "csp_enabled" in status
