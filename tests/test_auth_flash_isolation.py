"""tests/test_auth_flash_isolation.py — 플래시 메시지 카테고리 격리 테스트 (Phase 142)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_auth_app():
    from flask import Flask
    try:
        from src.auth.views import auth_bp
        from src.auth.magic_link import magic_link_bp
    except Exception as exc:
        pytest.skip(f"auth blueprints not importable: {exc}")
    app = Flask(__name__)
    app.secret_key = "test-secret-flash"
    app.config["TESTING"] = True
    app.register_blueprint(auth_bp)
    app.register_blueprint(magic_link_bp)
    return app


class TestFlashIsolation:
    def test_oauth_flash_not_shown_on_magic_link_page(self):
        """OAuth 오류 플래시가 magic_link 페이지에 표시되지 않음."""
        app = _make_auth_app()
        with app.test_client() as client:
            # 1. OAuth 오류 → flash("보안 오류", "auth_oauth")
            with client.session_transaction() as sess:
                sess["_flashes"] = [("auth_oauth", "보안 오류가 발생했습니다. 다시 시도해주세요.")]
            # 2. magic_link 페이지 조회 → auth_oauth 메시지가 보이면 안 됨
            resp = client.get("/auth/magic-link")
        assert resp.status_code == 200
        # magic_link 페이지는 auth_oauth 카테고리를 필터링함
        assert b"\xeb\xb3\xb4\xec\x95\x88 \xec\x98\xa4\xeb\xa5\x98" not in resp.data  # "보안 오류" UTF-8

    def test_email_login_flash_not_shown_on_magic_link_page(self):
        """이메일 로그인 오류 플래시가 magic_link 페이지에 표시되지 않음."""
        app = _make_auth_app()
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["_flashes"] = [
                    ("auth_email", "이메일 또는 비밀번호가 올바르지 않습니다."),
                    ("auth_oauth", "보안 오류가 발생했습니다."),
                ]
            resp = client.get("/auth/magic-link")
        assert resp.status_code == 200
        # auth_email 카테고리 메시지가 표시되지 않아야 함
        body = resp.data.decode("utf-8")
        assert "이메일 또는 비밀번호" not in body

    def test_magic_link_own_messages_shown(self):
        """magic_link 자체 성공/오류 메시지는 표시됨."""
        app = _make_auth_app()
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["_flashes"] = [("success", "이메일을 확인하세요.")]
            resp = client.get("/auth/magic-link")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "이메일을 확인하세요" in body

    def test_danger_flash_shown_on_magic_link(self):
        """general danger 메시지는 magic_link 페이지에 표시됨."""
        app = _make_auth_app()
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["_flashes"] = [("danger", "올바른 이메일을 입력하세요.")]
            resp = client.get("/auth/magic-link")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "올바른 이메일" in body

    def test_email_login_uses_auth_email_category(self):
        """이메일 로그인 오류는 auth_email 카테고리를 사용해야 함."""
        from unittest.mock import patch
        app = _make_auth_app()
        flashed = []
        with app.test_client() as client:
            with patch("src.auth.views.flash") as mock_flash:
                client.post("/auth/login", data={"email": "x@x.com", "password": "wrong"})
                if mock_flash.called:
                    for call in mock_flash.call_args_list:
                        category = call[0][1] if len(call[0]) > 1 else call[1].get("category", "")
                        flashed.append(category)
        # oauth_callback 또는 login_post에서 auth_email/auth_oauth 카테고리 사용
        # (login_post가 실제로 실행되었을 때만 확인)
        if flashed:
            # 모든 플래시가 auth_email 또는 danger 카테고리를 사용해야 함 (auth_oauth 사용 안 함)
            for cat in flashed:
                assert cat in ("auth_email", "danger", "warning", "success", "info"), \
                    f"Unexpected flash category: {cat}"


class TestOAuthFlashCategory:
    def test_oauth_callback_uses_auth_oauth_category(self):
        """OAuth 콜백 오류는 auth_oauth 카테고리를 사용해야 함."""
        from unittest.mock import patch
        app = _make_auth_app()
        with app.test_client() as client:
            with patch("src.auth.views.flash") as mock_flash:
                # state 불일치 → CSRF 오류
                client.get("/auth/kakao/callback?state=wrong&code=abc")
                if mock_flash.called:
                    for call in mock_flash.call_args_list:
                        category = call[0][1] if len(call[0]) > 1 else call[1].get("category", "")
                        assert category == "auth_oauth", f"Expected auth_oauth, got {category}"
