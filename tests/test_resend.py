"""tests/test_resend.py — Resend 이메일 어댑터 테스트 (Phase 133/134)."""
import os
import pytest
from unittest.mock import MagicMock, patch


class TestSendEmail:
    def test_dry_run_returns_false(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.notifications.email_resend import send_email
        result = send_email("test@example.com", "제목", "<p>내용</p>")
        assert result is False

    def test_no_api_key_returns_false(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        from src.notifications.email_resend import send_email
        result = send_email("test@example.com", "제목", "<p>내용</p>")
        assert result is False

    def test_sends_with_api_key(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "msg_123"}

        with patch("requests.post", return_value=mock_resp):
            from src.notifications import email_resend
            import importlib
            importlib.reload(email_resend)
            from src.notifications.email_resend import send_email
            result = send_email("test@example.com", "제목", "<p>내용</p>")

        assert result is True

    def test_returns_false_on_http_error(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 422
        mock_resp.text = "Unprocessable"

        with patch("requests.post", return_value=mock_resp):
            from src.notifications.email_resend import send_email
            result = send_email("bad_email", "제목", "<p>내용</p>")

        assert result is False

    def test_custom_from_email(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

        sent_payloads = []
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "msg_custom"}

        def mock_post(url, headers, json, timeout):
            sent_payloads.append(json)
            return mock_resp

        with patch("requests.post", side_effect=mock_post):
            from src.notifications.email_resend import send_email
            send_email("test@example.com", "제목", "<p>내용</p>", from_email="custom@example.com")

        assert sent_payloads[0]["from"] == "custom@example.com"


class TestSendAdminEmail:
    def test_no_admin_emails_returns_false(self, monkeypatch):
        monkeypatch.delenv("ADMIN_EMAILS", raising=False)
        from src.notifications.email_resend import send_admin_email
        result = send_admin_email("제목", "<p>내용</p>")
        assert result is False

    def test_sends_to_all_admin_emails(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        monkeypatch.setenv("RESEND_API_KEY", "re_test")
        monkeypatch.setenv("ADMIN_EMAILS", "admin1@example.com,admin2@example.com")

        call_count = [0]
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "msg"}

        def mock_post(*args, **kwargs):
            call_count[0] += 1
            return mock_resp

        with patch("requests.post", side_effect=mock_post):
            from src.notifications.email_resend import send_admin_email
            result = send_admin_email("관리자 알림", "<p>내용</p>")

        assert call_count[0] == 2
