"""tests/test_login_remember_session.py — 자동 로그인(remember) → 영구 세션 제어."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _User:
    user_id = "u1"
    email = "consumer@example.com"
    name = "소비자"
    role = "seller"


@pytest.fixture
def app():
    from src.order_webhook import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def test_consumer_without_remember_is_not_permanent(app):
    """소비자가 자동로그인 안 하면 브라우저 세션(닫으면 로그아웃)."""
    from src.auth import views
    from flask import session
    with app.test_request_context("/"):
        views.establish_session(_User(), remember=False)
        assert session.permanent is False


def test_consumer_with_remember_is_permanent(app):
    """자동 로그인 선택 시 영구 세션 유지."""
    from src.auth import views
    from flask import session
    with app.test_request_context("/"):
        views.establish_session(_User(), remember=True)
        assert session.permanent is True


def test_admin_is_always_permanent(app):
    """관리자(오너)는 자동로그인 미선택이어도 유지(예외)."""
    from src.auth import views
    from flask import session
    with app.test_request_context("/"):
        views.establish_session(_User(), role="admin", remember=False)
        assert session.permanent is True


def test_login_page_has_remember_checkbox(client):
    html = client.get("/auth/login").get_data(as_text=True)
    assert 'id="rememberMe"' in html
    assert "자동 로그인" in html
    assert 'name="remember"' in html          # 이메일 폼 hidden
    assert "social-login-link" in html         # 소셜 링크에 remember 부착용 클래스


def test_session_remember_lifetime_configured(app):
    from datetime import timedelta
    assert isinstance(app.config.get("PERMANENT_SESSION_LIFETIME"), timedelta)
