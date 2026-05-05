"""tests/test_resend.py — Resend 이메일 어댑터 테스트 (Phase 133)."""
from __future__ import annotations

import os
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_import():
    """모듈 임포트 성공."""
    from src.notifications.email_resend import send_email, health_check
    assert callable(send_email)
    assert callable(health_check)


def test_noop_when_key_missing(monkeypatch):
    """RESEND_API_KEY 미설정 시 sent=False 반환."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    from src.notifications.email_resend import send_email
    result = send_email(to="test@example.com", subject="테스트", html="<p>테스트</p>")
    assert result["sent"] is False
    assert "RESEND_API_KEY" in result.get("reason", "")


def test_dry_run(monkeypatch):
    """ADAPTER_DRY_RUN=1 시 외부 호출 차단."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_12345678")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.notifications.email_resend import send_email
    result = send_email(to="test@example.com", subject="테스트", html="<p>테스트</p>")
    assert result["sent"] is False
    assert result.get("_dry_run") is True


def test_send_success(monkeypatch):
    """키 설정 + API 성공 시 sent=True 반환."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_12345678")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "email_id_123"}

    with mock.patch("requests.post", return_value=FakeResp()):
        from src.notifications import email_resend
        result = email_resend.send_email(
            to="user@example.com",
            subject="주문 확인",
            html="<p>주문이 완료되었습니다.</p>",
        )
    assert result["sent"] is True
    assert result["id"] == "email_id_123"


def test_send_to_list(monkeypatch):
    """to가 목록일 때 처리."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_12345678")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "multi_email_id"}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["payload"] = json
        return FakeResp()

    with mock.patch("requests.post", side_effect=fake_post):
        from src.notifications import email_resend
        email_resend.send_email(
            to=["a@example.com", "b@example.com"],
            subject="다중 수신",
            html="<p>테스트</p>",
        )
    assert isinstance(captured["payload"]["to"], list)
    assert len(captured["payload"]["to"]) == 2


def test_health_check_missing_key(monkeypatch):
    """키 미설정 시 status=missing."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    from src.notifications.email_resend import health_check
    result = health_check()
    assert result["status"] == "missing"


def test_health_check_ok(monkeypatch):
    """키 설정 + API 200 시 status=ok."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_12345678")

    class FakeResp:
        status_code = 200

        def json(self):
            return {"data": [{"id": "domain1"}, {"id": "domain2"}]}

    with mock.patch("requests.get", return_value=FakeResp()):
        from src.notifications import email_resend
        result = email_resend.health_check()
    assert result["status"] == "ok"
    assert result["domains"] == 2


def test_health_check_api_fail(monkeypatch):
    """API 오류 시 status=fail."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_12345678")

    class FakeResp:
        status_code = 401

        def json(self):
            return {}

    with mock.patch("requests.get", return_value=FakeResp()):
        from src.notifications import email_resend
        result = email_resend.health_check()
    assert result["status"] == "fail"
    assert result.get("code") == 401


def test_send_uses_from_env(monkeypatch):
    """RESEND_FROM_EMAIL 환경변수 사용."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_12345678")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "custom@example.com")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "x"}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["payload"] = json
        return FakeResp()

    with mock.patch("requests.post", side_effect=fake_post):
        from src.notifications import email_resend
        email_resend.send_email(to="u@e.com", subject="s", html="<p>h</p>")

    assert captured["payload"]["from"] == "custom@example.com"
