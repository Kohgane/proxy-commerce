"""tests/test_callback_uri.py — Phase 175: _callback_uri / _resolve_oauth_base_url 단위 테스트.

검증 항목:
- OAUTH_REDIRECT_BASE_URL env 최우선
- APP_BASE_URL env 폴백
- 요청 컨텍스트 기반 생성 (ProxyFix 적용 시 https scheme 반영)
- 요청 컨텍스트 없을 때 폴백
- 정규화: 끝슬래시 제거, host 소문자, https 강제 (localhost 예외)
- oauth_start와 oauth_callback이 동일한 redirect_uri를 사용
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _clear_oauth_envs(monkeypatch):
    """각 테스트 전 OAuth 베이스 URL 관련 env 초기화."""
    monkeypatch.delenv("OAUTH_REDIRECT_BASE_URL", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)


# ---------------------------------------------------------------------------
# _callback_uri / _resolve_oauth_base_url 테스트 (no request context)
# ---------------------------------------------------------------------------

class TestCallbackUriNoRequestContext:
    """요청 컨텍스트 없이 env 기반 동작 검증."""

    def test_oauth_redirect_base_url_takes_priority(self, monkeypatch):
        """OAUTH_REDIRECT_BASE_URL이 APP_BASE_URL보다 우선."""
        monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "https://custom.example.com")
        monkeypatch.setenv("APP_BASE_URL", "https://other.example.com")
        from src.auth.views import _callback_uri
        uri = _callback_uri("google")
        assert uri == "https://custom.example.com/auth/google/callback"

    def test_app_base_url_used_when_no_override(self, monkeypatch):
        """APP_BASE_URL이 설정돼 있으면 그 값을 사용."""
        monkeypatch.setenv("APP_BASE_URL", "https://myapp.example.com")
        from src.auth.views import _callback_uri
        uri = _callback_uri("google")
        assert uri == "https://myapp.example.com/auth/google/callback"

    def test_fallback_when_no_env_no_context(self, monkeypatch):
        """env 없고 요청 컨텍스트 없으면 폴백 도메인 사용."""
        from src.auth.views import _callback_uri
        uri = _callback_uri("google")
        # 폴백 도메인 (kohganepercentiii.com) 사용
        assert "/auth/google/callback" in uri
        assert uri.startswith("https://")

    def test_provider_path_correct_for_all_providers(self, monkeypatch):
        """각 프로바이더별 경로가 /auth/<provider>/callback 형식."""
        monkeypatch.setenv("APP_BASE_URL", "https://example.com")
        from src.auth.views import _callback_uri
        assert _callback_uri("google").endswith("/auth/google/callback")
        assert _callback_uri("kakao").endswith("/auth/kakao/callback")
        assert _callback_uri("naver").endswith("/auth/naver/callback")

    def test_trailing_slash_stripped_from_env(self, monkeypatch):
        """env 값에 끝 슬래시가 있어도 정규화로 제거."""
        monkeypatch.setenv("APP_BASE_URL", "https://example.com/")
        from src.auth.views import _callback_uri
        uri = _callback_uri("google")
        assert "//auth" not in uri
        assert uri == "https://example.com/auth/google/callback"

    def test_host_lowercased(self, monkeypatch):
        """host가 대문자여도 소문자로 정규화."""
        monkeypatch.setenv("APP_BASE_URL", "https://MyDomain.Example.COM")
        from src.auth.views import _callback_uri
        uri = _callback_uri("google")
        assert "mydomain.example.com" in uri

    def test_http_forced_to_https_for_non_localhost(self, monkeypatch):
        """비 localhost env에 http scheme이 있으면 https로 강제."""
        monkeypatch.setenv("APP_BASE_URL", "http://myapp.example.com")
        from src.auth.views import _callback_uri
        uri = _callback_uri("google")
        assert uri.startswith("https://")

    def test_localhost_keeps_http(self, monkeypatch):
        """localhost는 http 허용."""
        monkeypatch.setenv("APP_BASE_URL", "http://localhost:5000")
        from src.auth.views import _callback_uri
        uri = _callback_uri("google")
        assert uri.startswith("http://localhost:5000")

    def test_127_0_0_1_keeps_http(self, monkeypatch):
        """127.0.0.1은 http 허용."""
        monkeypatch.setenv("APP_BASE_URL", "http://127.0.0.1:5000")
        from src.auth.views import _callback_uri
        uri = _callback_uri("google")
        assert uri.startswith("http://127.0.0.1:5000")


# ---------------------------------------------------------------------------
# _callback_uri 요청 컨텍스트 기반 테스트
# ---------------------------------------------------------------------------

class TestCallbackUriWithRequestContext:
    """Flask 요청 컨텍스트 내에서 host 기반 생성 검증."""

    @pytest.fixture
    def app(self):
        from flask import Flask
        _app = Flask(__name__)
        _app.config["TESTING"] = True
        _app.secret_key = "test-secret-key"
        return _app

    def test_uses_request_host_when_no_env(self, app):
        """env 없으면 요청 host에서 URI를 생성."""
        from src.auth.views import _callback_uri
        with app.test_request_context(
            "/auth/google/start",
            headers={"Host": "myhost.example.com"},
            environ_base={"wsgi.url_scheme": "https"},
        ):
            uri = _callback_uri("google")
        assert "myhost.example.com" in uri
        assert uri.endswith("/auth/google/callback")

    def test_env_overrides_request_host(self, monkeypatch, app):
        """env가 있으면 요청 host보다 env 우선."""
        monkeypatch.setenv("APP_BASE_URL", "https://env.example.com")
        from src.auth.views import _callback_uri
        with app.test_request_context(
            "/auth/google/start",
            headers={"Host": "requesthost.example.com"},
        ):
            uri = _callback_uri("google")
        assert "env.example.com" in uri
        assert "requesthost.example.com" not in uri

    def test_x_forwarded_proto_https(self, app):
        """X-Forwarded-Proto: https가 반영되면 https scheme 사용."""
        from src.auth.views import _callback_uri
        # ProxyFix가 적용됐다면 request.scheme가 https로 잡힘.
        # 테스트에서는 wsgi.url_scheme을 직접 설정해 시뮬레이션.
        with app.test_request_context(
            "/auth/google/start",
            headers={"Host": "myapp.example.com"},
            environ_base={"wsgi.url_scheme": "https"},
        ):
            uri = _callback_uri("google")
        assert uri.startswith("https://")

    def test_start_and_callback_produce_same_uri(self, app):
        """oauth_start와 oauth_callback에서 동일한 redirect_uri 보장."""
        from src.auth.views import _callback_uri
        host_header = {"Host": "same-host.example.com"}
        environ = {"wsgi.url_scheme": "https"}
        with app.test_request_context("/auth/google/start", headers=host_header, environ_base=environ):
            uri_start = _callback_uri("google")
        with app.test_request_context("/auth/google/callback", headers=host_header, environ_base=environ):
            uri_callback = _callback_uri("google")
        assert uri_start == uri_callback


# ---------------------------------------------------------------------------
# env 별칭 폴백 테스트 (Google GOOGLE_CLIENT_ID → GOOGLE_OAUTH_CLIENT_ID)
# ---------------------------------------------------------------------------

class TestGoogleEnvAliasFallback:
    """레거시 GOOGLE_CLIENT_ID가 설정돼 있으면 GoogleProvider.is_configured=True."""

    def test_legacy_env_makes_google_configured(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "legacy-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "legacy-secret")
        from src.auth.providers.google import GoogleProvider
        p = GoogleProvider()
        assert p.is_configured
        assert p.client_id == "legacy-client-id"

    def test_standard_env_takes_priority_over_legacy(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "standard-id")
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "legacy-id")
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "standard-secret")
        from src.auth.providers.google import GoogleProvider
        p = GoogleProvider()
        assert p.client_id == "standard-id"

    def test_not_configured_when_both_missing(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        from src.auth.providers.google import GoogleProvider
        assert not GoogleProvider().is_configured


# ---------------------------------------------------------------------------
# 로그인 화면 smoke 테스트: redirect_uri 렌더 확인
# ---------------------------------------------------------------------------

class TestLoginPageRedirectUriSmoke:
    """로그인 화면에 redirect_uri 가 렌더되는지 스모크 테스트."""

    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APP_BASE_URL", "https://smoke.example.com")
        from flask import Flask
        _app = Flask(__name__)
        _app.config["TESTING"] = True
        _app.secret_key = "smoke-test-secret"
        from src.auth.views import auth_bp
        _app.register_blueprint(auth_bp)
        with _app.test_client() as c:
            yield c

    def test_login_page_contains_callback_uri(self, client):
        rv = client.get("/auth/login")
        assert rv.status_code == 200
        body = rv.data.decode("utf-8", errors="replace")
        # redirect_uris 섹션 또는 콜백 URI 문자열이 포함되어야 함
        assert "/auth/google/callback" in body or "smoke.example.com" in body
