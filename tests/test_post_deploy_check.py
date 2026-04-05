"""Tests for scripts/post_deploy_check.py."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.post_deploy_check import check_endpoint, run_healthcheck, send_telegram


class TestCheckEndpoint:
    def test_success_on_first_attempt(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch('scripts.post_deploy_check.requests.get', return_value=mock_resp) as mock_get:
            ok, error = check_endpoint('http://example.com/health', retries=3, interval=0)

        assert ok is True
        assert error == ''
        assert mock_get.call_count == 1

    def test_failure_then_success_retries(self):
        fail_resp = MagicMock()
        fail_resp.status_code = 500
        ok_resp = MagicMock()
        ok_resp.status_code = 200

        with patch('scripts.post_deploy_check.requests.get', side_effect=[fail_resp, ok_resp]):
            with patch('scripts.post_deploy_check.time.sleep'):
                ok, error = check_endpoint('http://example.com/health', retries=3, interval=1)

        assert ok is True
        assert error == ''

    def test_all_retries_exhausted_returns_failure(self):
        fail_resp = MagicMock()
        fail_resp.status_code = 503

        with patch('scripts.post_deploy_check.requests.get', return_value=fail_resp):
            with patch('scripts.post_deploy_check.time.sleep'):
                ok, error = check_endpoint('http://example.com/health', retries=3, interval=1)

        assert ok is False
        assert 'HTTP 503' in error

    def test_request_exception_triggers_retry(self):
        with patch('scripts.post_deploy_check.requests.get',
                   side_effect=requests.ConnectionError('refused')):
            with patch('scripts.post_deploy_check.time.sleep'):
                ok, error = check_endpoint('http://example.com/health', retries=2, interval=1)

        assert ok is False
        assert 'refused' in error


class TestRunHealthcheck:
    def test_success_when_both_endpoints_ok(self):
        ok_resp = MagicMock()
        ok_resp.status_code = 200

        with patch('scripts.post_deploy_check.requests.get', return_value=ok_resp):
            ok, err = run_healthcheck('http://example.com', 'staging', retries=1, interval=0)

        assert ok is True
        assert err == ''

    def test_failure_when_health_endpoint_fails(self):
        fail_resp = MagicMock()
        fail_resp.status_code = 500

        with patch('scripts.post_deploy_check.requests.get', return_value=fail_resp):
            with patch('scripts.post_deploy_check.time.sleep'):
                ok, err = run_healthcheck('http://example.com', 'staging', retries=1, interval=0)

        assert ok is False
        assert '/health' in err

    def test_soft_fail_when_ready_endpoint_fails(self):
        health_ok = MagicMock()
        health_ok.status_code = 200
        ready_fail = MagicMock()
        ready_fail.status_code = 503

        with patch('scripts.post_deploy_check.requests.get', side_effect=[health_ok, ready_fail]):
            with patch('scripts.post_deploy_check.time.sleep'):
                ok, err = run_healthcheck('http://example.com', 'staging', retries=1, interval=0)

        # soft-fail: /health is OK so deploy is treated as succeeded
        assert ok is True
        assert err == ''


class TestSendTelegram:
    def test_sends_message_when_credentials_present(self, monkeypatch):
        monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'bot123:TOKEN')
        monkeypatch.setenv('TELEGRAM_CHAT_ID', '456789')

        with patch('scripts.post_deploy_check.requests.post') as mock_post:
            send_telegram('test message')

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert 'test message' in str(call_kwargs)

    def test_skips_when_no_credentials(self, monkeypatch):
        monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
        monkeypatch.delenv('TELEGRAM_CHAT_ID', raising=False)

        with patch('scripts.post_deploy_check.requests.post') as mock_post:
            send_telegram('test message')

        mock_post.assert_not_called()


class TestMain:
    def test_exits_1_when_all_retries_exhausted(self, monkeypatch):
        monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
        monkeypatch.delenv('TELEGRAM_CHAT_ID', raising=False)
        monkeypatch.setenv('APP_VERSION', 'test-sha')

        fail_resp = MagicMock()
        fail_resp.status_code = 500

        with patch('scripts.post_deploy_check.requests.get', return_value=fail_resp):
            with patch('scripts.post_deploy_check.time.sleep'):
                with pytest.raises(SystemExit) as exc_info:
                    from scripts.post_deploy_check import main
                    main(['--url', 'http://example.com', '--env', 'staging',
                          '--retries', '2', '--interval', '0'])

        assert exc_info.value.code == 1
