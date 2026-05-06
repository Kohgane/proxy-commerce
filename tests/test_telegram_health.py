"""tests/test_telegram_health.py — 텔레그램 health_check 테스트 (Phase 136)."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTelegramHealthCheck:
    def test_missing_token(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        from src.notifications.telegram import health_check
        result = health_check()
        assert result["status"] == "missing"
        assert "TELEGRAM_BOT_TOKEN" in result["hint"]

    def test_missing_chat_id(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        from src.notifications.telegram import health_check
        result = health_check()
        assert result["status"] == "missing"
        assert "TELEGRAM_CHAT_ID" in result["hint"]

    def test_getme_fail(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bad:token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        with patch("requests.get") as mock_get:
            resp = MagicMock()
            resp.status_code = 401
            resp.json.return_value = {"ok": False}
            mock_get.return_value = resp

            from src.notifications.telegram import health_check
            result = health_check()

        assert result["status"] == "fail"
        assert result.get("stage") == "getMe"

    def test_getchat_fail(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "good:token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "bad_chat_id")

        with patch("requests.get") as mock_get:
            def side_effect(url, *args, **kwargs):
                resp = MagicMock()
                if "getMe" in url:
                    resp.status_code = 200
                    resp.json.return_value = {"ok": True, "result": {"username": "TestBot"}}
                else:
                    resp.status_code = 400
                    resp.json.return_value = {"ok": False, "description": "Bad Request: chat not found"}
                return resp

            mock_get.side_effect = side_effect

            from src.notifications.telegram import health_check
            result = health_check()

        assert result["status"] == "fail"
        assert result.get("stage") == "getChat"

    def test_ok_status(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "good:token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        with patch("requests.get") as mock_get:
            def side_effect(url, *args, **kwargs):
                resp = MagicMock()
                resp.status_code = 200
                if "getMe" in url:
                    resp.json.return_value = {
                        "ok": True,
                        "result": {"username": "KoGaneBot", "first_name": "코가네봇"},
                    }
                else:
                    resp.json.return_value = {
                        "ok": True,
                        "result": {"title": "코가네 알림방", "id": 12345},
                    }
                return resp

            mock_get.side_effect = side_effect

            from src.notifications.telegram import health_check
            result = health_check()

        assert result["status"] == "ok"
        assert result["bot"] == "KoGaneBot"
        assert "코가네 알림방" in str(result.get("chat_title", ""))

    def test_getchat_network_error(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "good:token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        with patch("requests.get") as mock_get:
            def side_effect(url, *args, **kwargs):
                if "getMe" in url:
                    resp = MagicMock()
                    resp.status_code = 200
                    resp.json.return_value = {"ok": True, "result": {"username": "Bot"}}
                    return resp
                raise ConnectionError("Network error")

            mock_get.side_effect = side_effect

            from src.notifications.telegram import health_check
            result = health_check()

        assert result["status"] == "fail"
        assert result.get("stage") == "getChat"
