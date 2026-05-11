"""tests/test_oauth_setup_page.py — /admin/oauth-setup 페이지 테스트 (Phase 150)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-secret-oauth-setup"
    with app.test_client() as c:
        yield c


@pytest.fixture
def admin_client(client):
    """관리자 세션이 있는 클라이언트."""
    import os

    admin_email = "admin@test.com"
    os.environ.setdefault("ADMIN_EMAILS", admin_email)

    with client.session_transaction() as sess:
        sess["user_id"] = "test-admin-user"
        sess["user_role"] = "admin"
        sess["email"] = admin_email

    return client


class TestOAuthSetupPage:
    def test_oauth_setup_requires_login(self, client):
        """로그인하지 않으면 /auth/login으로 리디렉트."""
        resp = client.get("/admin/oauth-setup")
        assert resp.status_code in (302, 301)
        location = resp.headers.get("Location", "")
        assert "/auth/login" in location or "/admin" in location

    def test_oauth_setup_returns_200_for_admin(self, admin_client):
        """관리자 세션이면 200 반환."""
        resp = admin_client.get("/admin/oauth-setup")
        assert resp.status_code == 200

    def test_oauth_setup_contains_google_section(self, admin_client):
        """Google OAuth 섹션 포함."""
        html = admin_client.get("/admin/oauth-setup").get_data(as_text=True)
        assert "Google" in html
        assert "callback" in html.lower() or "/auth/google" in html

    def test_oauth_setup_contains_naver_section(self, admin_client):
        """Naver OAuth 섹션 포함."""
        html = admin_client.get("/admin/oauth-setup").get_data(as_text=True)
        assert "Naver" in html or "네이버" in html

    def test_oauth_setup_contains_kakao_section(self, admin_client):
        """Kakao OAuth 섹션 포함."""
        html = admin_client.get("/admin/oauth-setup").get_data(as_text=True)
        assert "Kakao" in html or "카카오" in html

    def test_oauth_setup_has_copy_buttons(self, admin_client):
        """클립보드 복사 버튼 포함."""
        html = admin_client.get("/admin/oauth-setup").get_data(as_text=True)
        assert "clipboard" in html or "복사" in html

    def test_oauth_setup_contains_naver_warning(self, admin_client):
        """Naver Commerce API와 혼동 주의 경고 포함."""
        html = admin_client.get("/admin/oauth-setup").get_data(as_text=True)
        # Commerce API와 로그인 OAuth가 다르다는 경고 및 Naver Developers 링크 포함
        assert "주의" in html or "apicenter.commerce.naver.com" in html
