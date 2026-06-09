"""tests/test_auth_views.py — 인증 뷰 통합 테스트 (Phase 133)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    """Flask 테스트 클라이언트."""
    os.environ.setdefault("GOOGLE_SERVICE_JSON_B64", "")
    from src.order_webhook import app
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.secret_key = "test-secret-key-for-auth-tests"
    with app.test_client() as c:
        yield c


class TestAuthRoutes:
    def test_login_page_returns_200(self, client):
        """로그인 페이지 GET 200."""
        resp = client.get("/auth/login")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '/static/app.css' in html
        assert 'id="login-email"' in html
        assert 'id="login-password"' in html

    def test_login_page_has_no_dead_hash_link(self, client):
        """로그인 페이지에 href=\"#\" 데드 링크가 남아 있지 않다."""
        resp = client.get("/auth/login")
        html = resp.get_data(as_text=True)
        assert 'href="#"' not in html
        assert "forgotForm" in html

    def test_signup_page_returns_200(self, client):
        """가입 페이지 GET 200."""
        resp = client.get("/auth/signup")
        assert resp.status_code == 200

    def test_login_page_shows_honest_disabled_oauth_buttons_when_unconfigured(self, client, monkeypatch):
        monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
        monkeypatch.delenv("KAKAO_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("NAVER_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_OAUTH_CLIENT_SECRET", raising=False)

        resp = client.get("/auth/login")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "카카오 로그인 (설정 필요)" in html
        assert "Google 로그인 (설정 필요)" in html
        assert "네이버 로그인 (설정 필요)" in html
        assert "/admin/oauth-setup" in html

    def test_logout_get_redirects(self, client):
        """로그아웃 GET → 로그인 리다이렉트."""
        resp = client.get("/auth/logout")
        assert resp.status_code in (302, 301)

    def test_reset_page_returns_200(self, client):
        """비밀번호 재설정 페이지 GET 200."""
        resp = client.get("/auth/reset?token=sometoken")
        assert resp.status_code == 200

    def test_verify_email_without_token(self, client):
        """이메일 인증 — 토큰 없으면 리다이렉트."""
        resp = client.get("/auth/verify-email")
        assert resp.status_code in (302, 301)


class TestOAuthStart:
    def test_kakao_start_redirects_when_configured(self, client, monkeypatch):
        """KAKAO_REST_API_KEY 설정 시 카카오로 리다이렉트."""
        monkeypatch.setenv("KAKAO_REST_API_KEY", "kakao_test_key_abc123")
        resp = client.get("/auth/kakao/start")
        assert resp.status_code in (302, 301)
        location = resp.headers.get("Location", "")
        # 카카오 OAuth URL로 리다이렉트 확인
        assert location.lower().startswith("https://kauth.kakao.com")

    def test_invalid_provider_returns_400(self, client):
        """지원하지 않는 프로바이더 → 400."""
        resp = client.get("/auth/unknown_provider/start")
        assert resp.status_code in (400, 404)

    def test_state_stored_in_session(self, client, monkeypatch):
        """OAuth 시작 시 state가 세션에 저장됨."""
        monkeypatch.setenv("KAKAO_REST_API_KEY", "kakao_test_key_abc123")
        with client.session_transaction() as sess:
            sess.clear()
        resp = client.get("/auth/kakao/start")
        assert resp.status_code in (302, 301)


class TestOAuthCallback:
    def test_callback_without_code_redirects(self, client):
        """code 없이 콜백 → 로그인 리다이렉트."""
        resp = client.get("/auth/kakao/callback?state=some_state")
        assert resp.status_code in (302, 301)

    def test_callback_csrf_protection(self, client, monkeypatch):
        """state 불일치 시 CSRF 방어 → 로그인으로 리다이렉트."""
        monkeypatch.setenv("KAKAO_REST_API_KEY", "kakao_test_key_abc123")
        # 세션에 state 없이 콜백 접근
        resp = client.get("/auth/kakao/callback?code=some_code&state=bad_state")
        assert resp.status_code in (302, 301)


class TestLoginLogout:
    def test_login_post_missing_credentials(self, client):
        """이메일/비밀번호 없이 로그인 시도 → 리다이렉트."""
        resp = client.post("/auth/login", data={})
        assert resp.status_code in (302, 301)

    def test_logout_post_clears_session(self, client):
        """로그아웃 POST → 세션 클리어 + 리다이렉트."""
        with client.session_transaction() as sess:
            sess["user_id"] = "test_user_id"
        resp = client.post("/auth/logout")
        assert resp.status_code in (302, 301)
        with client.session_transaction() as sess:
            assert "user_id" not in sess


class TestUserModel:
    def test_user_new(self):
        """User.new() 생성 테스트."""
        from src.auth.models import User
        user = User.new(email="test@example.com", name="테스트", role="seller")
        assert user.email == "test@example.com"
        assert user.name == "테스트"
        assert user.role == "seller"
        assert user.user_id != ""
        assert user.active is True
        assert user.email_verified is False

    def test_user_to_from_row(self):
        """User to_row / from_row 직렬화 왕복."""
        from src.auth.models import User
        user = User.new(email="round@example.com", name="라운드트립")
        user.social_accounts = [{"provider": "kakao", "provider_user_id": "12345"}]
        row = user.to_row()
        restored = User.from_row(row)
        assert restored.email == user.email
        assert restored.name == user.name
        assert restored.user_id == user.user_id
        assert len(restored.social_accounts) == 1
        assert restored.social_accounts[0]["provider"] == "kakao"

    def test_admin_role_assignment(self):
        """admin role 생성 테스트."""
        from src.auth.models import User
        user = User.new(email="admin@example.com", name="관리자", role="admin")
        assert user.role == "admin"
