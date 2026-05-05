"""tests/test_auth_providers.py — 인증 프로바이더 테스트 (Phase 133)."""
from __future__ import annotations

import os
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Kakao Provider 테스트
# ---------------------------------------------------------------------------

class TestKakaoProvider:
    def test_import(self):
        """KakaoProvider 임포트 성공."""
        from src.auth.providers.kakao import KakaoProvider
        assert KakaoProvider.name == "kakao"

    def test_not_configured_without_key(self, monkeypatch):
        """KAKAO_REST_API_KEY 미설정 시 is_configured=False."""
        monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
        from src.auth.providers.kakao import KakaoProvider
        p = KakaoProvider()
        assert not p.is_configured

    def test_configured_with_key(self, monkeypatch):
        """KAKAO_REST_API_KEY 설정 시 is_configured=True."""
        monkeypatch.setenv("KAKAO_REST_API_KEY", "kakao_test_key_abc123")
        from src.auth.providers.kakao import KakaoProvider
        p = KakaoProvider()
        assert p.is_configured

    def test_get_authorize_url(self, monkeypatch):
        """인증 URL 생성."""
        monkeypatch.setenv("KAKAO_REST_API_KEY", "kakao_test_key_abc123")
        from src.auth.providers.kakao import KakaoProvider
        p = KakaoProvider()
        url = p.get_authorize_url(state="test_state", redirect_uri="https://example.com/callback")
        assert "kauth.kakao.com" in url
        assert "kakao_test_key_abc123" in url
        assert "test_state" in url

    def test_get_user_info_mapping(self, monkeypatch):
        """API 응답 → 내부 포맷 매핑."""
        monkeypatch.setenv("KAKAO_REST_API_KEY", "kakao_test_key_abc123")
        monkeypatch.setenv("KAKAO_CLIENT_SECRET", "kakao_secret_xyz")

        class FakeResp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "id": 12345678,
                    "kakao_account": {
                        "email": "user@kakao.com",
                        "profile": {
                            "nickname": "카카오유저",
                            "profile_image_url": "https://example.com/avatar.jpg",
                        },
                    },
                }

        with mock.patch("requests.get", return_value=FakeResp()):
            from src.auth.providers.kakao import KakaoProvider
            result = KakaoProvider().get_user_info("access_token_test")

        assert result["provider_user_id"] == "12345678"
        assert result["email"] == "user@kakao.com"
        assert result["name"] == "카카오유저"
        assert result["provider"] == "kakao"


# ---------------------------------------------------------------------------
# Google Provider 테스트
# ---------------------------------------------------------------------------

class TestGoogleProvider:
    def test_import(self):
        from src.auth.providers.google import GoogleProvider
        assert GoogleProvider.name == "google"

    def test_not_configured_without_keys(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
        from src.auth.providers.google import GoogleProvider
        assert not GoogleProvider().is_configured

    def test_configured_with_keys(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google_client_id_12345")
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google_client_secret_xyz")
        from src.auth.providers.google import GoogleProvider
        assert GoogleProvider().is_configured

    def test_get_authorize_url(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google_client_id_12345")
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google_client_secret_xyz")
        from src.auth.providers.google import GoogleProvider
        url = GoogleProvider().get_authorize_url(state="my_state", redirect_uri="https://ex.com/cb")
        assert "accounts.google.com" in url
        assert "my_state" in url
        assert "openid" in url

    def test_get_user_info_mapping(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google_client_id_12345")
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google_client_secret_xyz")

        class FakeResp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "sub": "google_user_sub_123",
                    "email": "user@gmail.com",
                    "name": "구글유저",
                    "picture": "https://example.com/google_avatar.jpg",
                }

        with mock.patch("requests.get", return_value=FakeResp()):
            from src.auth.providers.google import GoogleProvider
            result = GoogleProvider().get_user_info("access_token_test")

        assert result["provider_user_id"] == "google_user_sub_123"
        assert result["email"] == "user@gmail.com"
        assert result["provider"] == "google"


# ---------------------------------------------------------------------------
# Naver Provider 테스트
# ---------------------------------------------------------------------------

class TestNaverProvider:
    def test_import(self):
        from src.auth.providers.naver import NaverProvider
        assert NaverProvider.name == "naver"

    def test_not_configured_without_keys(self, monkeypatch):
        monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
        from src.auth.providers.naver import NaverProvider
        assert not NaverProvider().is_configured

    def test_configured_with_keys(self, monkeypatch):
        monkeypatch.setenv("NAVER_CLIENT_ID", "naver_client_id_abc")
        monkeypatch.setenv("NAVER_CLIENT_SECRET", "naver_client_secret_xyz")
        from src.auth.providers.naver import NaverProvider
        assert NaverProvider().is_configured

    def test_get_authorize_url(self, monkeypatch):
        monkeypatch.setenv("NAVER_CLIENT_ID", "naver_client_id_abc")
        monkeypatch.setenv("NAVER_CLIENT_SECRET", "naver_client_secret_xyz")
        from src.auth.providers.naver import NaverProvider
        url = NaverProvider().get_authorize_url(state="nv_state", redirect_uri="https://ex.com/cb")
        assert "nid.naver.com" in url
        assert "nv_state" in url

    def test_get_user_info_mapping(self, monkeypatch):
        monkeypatch.setenv("NAVER_CLIENT_ID", "naver_client_id_abc")
        monkeypatch.setenv("NAVER_CLIENT_SECRET", "naver_client_secret_xyz")

        class FakeResp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "resultcode": "00",
                    "message": "success",
                    "response": {
                        "id": "naver_user_id_123",
                        "email": "user@naver.com",
                        "name": "네이버유저",
                        "profile_image": "https://example.com/naver_avatar.jpg",
                    },
                }

        with mock.patch("requests.get", return_value=FakeResp()):
            from src.auth.providers.naver import NaverProvider
            result = NaverProvider().get_user_info("access_token_test")

        assert result["provider_user_id"] == "naver_user_id_123"
        assert result["email"] == "user@naver.com"
        assert result["provider"] == "naver"
