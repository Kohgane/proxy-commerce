"""tests/test_admin_resolver.py — admin_resolver.py 단위 테스트 (Phase 142)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestIsAdmin:
    def _make_user(self, role="seller", email="", social_accounts=None):
        from src.auth.models import User
        u = User(
            user_id="test-uid",
            email=email,
            name="Test User",
            role=role,
            social_accounts=social_accounts or [],
        )
        return u

    def test_admin_by_db_role(self, monkeypatch):
        from src.auth.admin_resolver import is_admin
        monkeypatch.setenv("ADMIN_EMAILS", "")
        user = self._make_user(role="admin", email="any@example.com")
        ok, rule = is_admin(user)
        assert ok is True
        assert rule == "db_role"

    def test_admin_by_email_env(self, monkeypatch):
        from src.auth.admin_resolver import is_admin
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com,boss@corp.com")
        user = self._make_user(role="seller", email="admin@example.com")
        ok, rule = is_admin(user)
        assert ok is True
        assert rule == "ADMIN_EMAILS"

    def test_not_admin_wrong_email(self, monkeypatch):
        from src.auth.admin_resolver import is_admin
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        user = self._make_user(role="seller", email="other@example.com")
        ok, rule = is_admin(user)
        assert ok is False

    def test_admin_by_kakao_id(self, monkeypatch):
        from src.auth.admin_resolver import is_admin
        monkeypatch.setenv("ADMIN_EMAILS", "")
        monkeypatch.setenv("ADMIN_KAKAO_IDS", "kakao123,kakao456")
        user = self._make_user(
            role="seller",
            email="",
            social_accounts=[{"provider": "kakao", "provider_user_id": "kakao123"}],
        )
        ok, rule = is_admin(user)
        assert ok is True
        assert rule == "ADMIN_KAKAO_IDS"

    def test_admin_by_google_sub(self, monkeypatch):
        from src.auth.admin_resolver import is_admin
        monkeypatch.setenv("ADMIN_EMAILS", "")
        monkeypatch.setenv("ADMIN_KAKAO_IDS", "")
        monkeypatch.setenv("ADMIN_GOOGLE_SUBS", "google_sub_xyz")
        user = self._make_user(
            role="seller",
            email="",
            social_accounts=[{"provider": "google", "provider_user_id": "google_sub_xyz"}],
        )
        ok, rule = is_admin(user)
        assert ok is True
        assert rule == "ADMIN_GOOGLE_SUBS"

    def test_admin_by_naver_id(self, monkeypatch):
        from src.auth.admin_resolver import is_admin
        monkeypatch.setenv("ADMIN_EMAILS", "")
        monkeypatch.setenv("ADMIN_KAKAO_IDS", "")
        monkeypatch.setenv("ADMIN_GOOGLE_SUBS", "")
        monkeypatch.setenv("ADMIN_NAVER_IDS", "naver_uid_001")
        user = self._make_user(
            role="seller",
            email="",
            social_accounts=[{"provider": "naver", "provider_user_id": "naver_uid_001"}],
        )
        ok, rule = is_admin(user)
        assert ok is True
        assert rule == "ADMIN_NAVER_IDS"

    def test_admin_by_bootstrap_email(self, monkeypatch):
        from src.auth.admin_resolver import is_admin
        monkeypatch.setenv("ADMIN_EMAILS", "")
        monkeypatch.setenv("ADMIN_KAKAO_IDS", "")
        monkeypatch.setenv("ADMIN_GOOGLE_SUBS", "")
        monkeypatch.setenv("ADMIN_NAVER_IDS", "")
        monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "bootstrap@corp.com")
        user = self._make_user(role="seller", email="bootstrap@corp.com")
        ok, rule = is_admin(user)
        assert ok is True
        assert rule == "ADMIN_BOOTSTRAP_EMAIL"

    def test_none_user_returns_false(self):
        from src.auth.admin_resolver import is_admin
        ok, rule = is_admin(None)
        assert ok is False
        assert rule == ""

    def test_seller_with_no_match(self, monkeypatch):
        from src.auth.admin_resolver import is_admin
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        monkeypatch.setenv("ADMIN_KAKAO_IDS", "")
        monkeypatch.setenv("ADMIN_GOOGLE_SUBS", "")
        monkeypatch.setenv("ADMIN_NAVER_IDS", "")
        monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "")
        user = self._make_user(role="seller", email="regular@example.com")
        ok, rule = is_admin(user)
        assert ok is False


class TestIsAdminSession:
    def test_session_role_admin(self, monkeypatch):
        from src.auth.admin_resolver import is_admin_session
        sess = {"user_id": "uid1", "user_role": "admin", "user_email": "x@x.com"}
        ok, rule = is_admin_session(sess)
        assert ok is True
        assert rule == "session_role"

    def test_session_email_in_admin_emails(self, monkeypatch):
        from src.auth.admin_resolver import is_admin_session
        monkeypatch.setenv("ADMIN_EMAILS", "adminx@corp.com")
        sess = {"user_id": "uid1", "user_role": "seller", "user_email": "adminx@corp.com"}
        ok, rule = is_admin_session(sess)
        assert ok is True
        assert rule == "ADMIN_EMAILS"

    def test_session_no_user_id(self):
        from src.auth.admin_resolver import is_admin_session
        ok, rule = is_admin_session({})
        assert ok is False

    def test_session_seller_not_in_admin_emails(self, monkeypatch):
        from src.auth.admin_resolver import is_admin_session
        monkeypatch.setenv("ADMIN_EMAILS", "admin@corp.com")
        sess = {"user_id": "uid1", "user_role": "seller", "user_email": "regular@corp.com"}
        ok, rule = is_admin_session(sess)
        assert ok is False


class TestResolveRoleForLogin:
    def test_admin_by_email(self, monkeypatch):
        from src.auth.admin_resolver import resolve_role_for_login
        monkeypatch.setenv("ADMIN_EMAILS", "test@admin.com")
        assert resolve_role_for_login("test@admin.com") == "admin"

    def test_seller_by_unknown_email(self, monkeypatch):
        from src.auth.admin_resolver import resolve_role_for_login
        monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
        assert resolve_role_for_login("user@example.com") == "seller"

    def test_admin_by_kakao_provider(self, monkeypatch):
        from src.auth.admin_resolver import resolve_role_for_login
        monkeypatch.setenv("ADMIN_EMAILS", "")
        monkeypatch.setenv("ADMIN_KAKAO_IDS", "kk999")
        result = resolve_role_for_login("", provider="kakao", provider_user_id="kk999")
        assert result == "admin"

    def test_seller_by_unknown_kakao_id(self, monkeypatch):
        from src.auth.admin_resolver import resolve_role_for_login
        monkeypatch.setenv("ADMIN_EMAILS", "")
        monkeypatch.setenv("ADMIN_KAKAO_IDS", "kk999")
        result = resolve_role_for_login("", provider="kakao", provider_user_id="kk000")
        assert result == "seller"
