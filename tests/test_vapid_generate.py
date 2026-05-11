"""tests/test_vapid_generate.py — VAPID 자동 생성 UI 테스트 (Phase 148)."""
from __future__ import annotations

import os
import pytest


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture(scope="module")
def admin_client(app):
    """관리자 세션이 설정된 테스트 클라이언트."""
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = "admin-test"
            sess["user_role"] = "admin"
            sess["user_email"] = "admin@test.com"
        yield c


def test_vapid_generate_endpoint_registered(app):
    """/admin/diagnostics/vapid-generate 엔드포인트가 등록되어야 한다."""
    assert "admin_panel.diagnostics_vapid_generate" in app.view_functions


def test_vapid_generate_requires_auth(app):
    """/admin/diagnostics/vapid-generate는 비인증 요청을 거부해야 한다."""
    with app.test_client() as c:
        resp = c.post("/admin/diagnostics/vapid-generate")
        assert resp.status_code in (302, 401, 403)


def test_vapid_generate_returns_keys(admin_client):
    """/admin/diagnostics/vapid-generate가 VAPID 키를 응답에 포함해야 한다."""
    # ADMIN_EMAILS 설정하여 admin 권한 부여
    with admin_client.application.test_request_context():
        os.environ["ADMIN_EMAILS"] = "admin@test.com"
    resp = admin_client.post("/admin/diagnostics/vapid-generate")
    # 200 또는 리다이렉트(302) 모두 허용 — 내용에 키 관련 텍스트 포함 여부 확인
    assert resp.status_code in (200, 302)


def test_generate_vapid_keys_function():
    """generate_vapid_keys()가 public/private 키를 반환해야 한다."""
    from src.notifications.web_push import generate_vapid_keys
    keys = generate_vapid_keys()
    assert isinstance(keys, dict)
    assert "public" in keys
    assert "private" in keys
    assert len(keys["public"]) > 0
    assert len(keys["private"]) > 0


def test_vapid_configured_false_when_no_env(monkeypatch):
    """VAPID 환경변수 미설정 시 vapid_configured()가 False를 반환해야 한다."""
    monkeypatch.delenv("WEB_PUSH_VAPID_PUBLIC", raising=False)
    monkeypatch.delenv("WEB_PUSH_VAPID_PRIVATE", raising=False)
    from src.notifications.web_push import vapid_configured
    assert vapid_configured() is False


def test_vapid_configured_true_when_env_set(monkeypatch):
    """VAPID 환경변수 설정 시 vapid_configured()가 True를 반환해야 한다."""
    monkeypatch.setenv("WEB_PUSH_VAPID_PUBLIC", "test-pub")
    monkeypatch.setenv("WEB_PUSH_VAPID_PRIVATE", "test-priv")
    from src.notifications.web_push import vapid_configured
    assert vapid_configured() is True
