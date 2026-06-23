"""tests/test_social_login_v14.py — v14 소셜 로그인 4종(구글·네이버·카카오·애플) 가드."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_apple_provider_honest_config(monkeypatch):
    for k in ("APPLE_CLIENT_ID", "APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_PRIVATE_KEY", "APPLE_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    from src.auth.providers.apple import AppleProvider
    assert AppleProvider().is_configured is False        # 키 없으면 비활성(가짜 활성 금지)
    monkeypatch.setenv("APPLE_CLIENT_ID", "com.kohgane.web")
    monkeypatch.setenv("APPLE_TEAM_ID", "TEAM123")
    monkeypatch.setenv("APPLE_KEY_ID", "KEY123")
    monkeypatch.setenv("APPLE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\\nX\\n-----END PRIVATE KEY-----")
    assert AppleProvider().is_configured is True


def test_apple_authorize_url_form_post(monkeypatch):
    monkeypatch.setenv("APPLE_CLIENT_ID", "com.kohgane.web")
    from src.auth.providers.apple import AppleProvider
    url = AppleProvider().get_authorize_url("st", "https://x/auth/apple/callback")
    assert "appleid.apple.com/auth/authorize" in url
    assert "response_mode=form_post" in url


def test_apple_in_provider_registry():
    from src.auth.views import _get_provider, _OAUTH_PROVIDERS
    assert "apple" in _OAUTH_PROVIDERS
    assert _get_provider("apple") is not None


def test_login_page_has_four_social():
    html = Path("src/auth/templates/auth/login.html").read_text(encoding="utf-8")
    assert "/auth/google/start" in html
    assert "/auth/naver/start" in html
    assert "/auth/kakao/start" in html
    assert "/auth/apple/start" in html
    assert "apple_status" in html


def test_onboarding_has_four_social():
    wiz = Path("src/seller_console/templates/onboarding_wizard.html").read_text(encoding="utf-8")
    for p in ("/auth/google/start", "/auth/naver/start", "/auth/kakao/start", "/auth/apple/start"):
        assert p in wiz


def test_callback_accepts_post_for_apple():
    # Apple form_post(POST) 대응 — 콜백 라우트가 POST 허용
    from src.order_webhook import app
    rules = [r for r in app.url_map.iter_rules() if "/auth/<provider>/callback" in str(r)]
    assert rules and "POST" in rules[0].methods
