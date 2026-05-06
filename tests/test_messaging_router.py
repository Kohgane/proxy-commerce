"""tests/test_messaging_router.py — 메시지 라우터 테스트 (Phase 134)."""
import os
import pytest
from unittest.mock import MagicMock, patch


def make_recipient(**kwargs):
    from src.messaging.models import Recipient
    defaults = {"name": "테스터", "locale": "ko"}
    defaults.update(kwargs)
    return Recipient(**defaults)


def make_router():
    """모든 채널이 비활성인 라우터."""
    with patch.dict(os.environ, {}, clear=False):
        for key in [
            "RESEND_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
            "KAKAO_ALIMTALK_API_KEY", "LINE_NOTIFY_TOKEN",
            "META_WHATSAPP_TOKEN", "WECHAT_APP_ID", "TWILIO_ACCOUNT_SID",
            "DISCORD_WEBHOOK_URL",
        ]:
            os.environ.pop(key, None)
        from src.messaging.router import MessageRouter
        with patch("src.messaging.router.MessageLog._get_ws", return_value=None):
            router = MessageRouter()
    return router


class TestLocaleRouting:
    def test_ko_priority(self):
        from src.messaging.router import LOCALE_PRIORITY
        order = LOCALE_PRIORITY["ko"]
        assert "kakao_alimtalk" in order
        assert order.index("kakao_alimtalk") < order.index("email")

    def test_ja_priority(self):
        from src.messaging.router import LOCALE_PRIORITY
        order = LOCALE_PRIORITY["ja"]
        assert "line" in order
        assert order.index("line") < order.index("email")

    def test_en_priority(self):
        from src.messaging.router import LOCALE_PRIORITY
        order = LOCALE_PRIORITY["en"]
        assert "whatsapp" in order
        assert order.index("whatsapp") < order.index("email")

    def test_zh_cn_priority(self):
        from src.messaging.router import LOCALE_PRIORITY
        order = LOCALE_PRIORITY["zh-CN"]
        assert "wechat" in order

    def test_default_fallback(self):
        from src.messaging.router import LOCALE_PRIORITY
        order = LOCALE_PRIORITY.get("unknown_locale", LOCALE_PRIORITY["default"])
        assert "email" in order


class TestHasRecipientId:
    def test_email_needs_email(self):
        from src.messaging.router import _has_recipient_id
        r = make_recipient(email="test@example.com")
        assert _has_recipient_id(r, "email") is True

    def test_email_fails_without_email(self):
        from src.messaging.router import _has_recipient_id
        r = make_recipient()
        assert _has_recipient_id(r, "email") is False

    def test_sms_needs_phone(self):
        from src.messaging.router import _has_recipient_id
        r = make_recipient(phone_e164="+821012345678")
        assert _has_recipient_id(r, "sms") is True

    def test_wechat_needs_openid(self):
        from src.messaging.router import _has_recipient_id
        r = make_recipient(wechat_openid="wx_openid_123")
        assert _has_recipient_id(r, "wechat") is True

    def test_whatsapp_uses_phone(self):
        from src.messaging.router import _has_recipient_id
        r = make_recipient(phone_e164="+821012345678")
        assert _has_recipient_id(r, "whatsapp") is True


class TestRouterSend:
    def test_all_channels_fail_returns_fallback(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with patch("src.messaging.router.MessageLog._get_ws", return_value=None):
            from src.messaging.router import MessageRouter
            router = MessageRouter()

        recipient = make_recipient(email="test@example.com", locale="ko")
        result = router.send(recipient, "order_received", {"order_id": "001"})
        # All channels inactive → fallback
        assert result.get("sent") is False or result.get("fallback") == "admin_telegram"

    def test_preferred_channels_override_locale(self, monkeypatch):
        """preferred_channels가 locale 우선순위를 override한다."""
        monkeypatch.setenv("RESEND_API_KEY", "re_test")
        from src.messaging.router import LOCALE_PRIORITY
        # ko 기본은 kakao 우선이지만 preferred_channels=[email] 이면 email 먼저
        with patch("src.messaging.router.MessageLog._get_ws", return_value=None):
            from src.messaging.router import MessageRouter
            router = MessageRouter()

        mock_email_ch = MagicMock()
        mock_email_ch.is_active = True
        mock_email_ch.send.return_value = MagicMock(sent=True, channel="email", provider_msg_id=None, error=None, to_dict=lambda: {"sent": True, "channel": "email"})
        router.channels["email"] = mock_email_ch

        recipient = make_recipient(
            email="test@example.com",
            locale="ko",
            preferred_channels=["email"],
        )
        result = router.send(recipient, "order_shipped", {"order_id": "002"})
        mock_email_ch.send.assert_called_once()

    def test_skips_inactive_channel(self, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        with patch("src.messaging.router.MessageLog._get_ws", return_value=None):
            from src.messaging.router import MessageRouter
            router = MessageRouter()

        # Email channel should be inactive
        assert router.channels["email"].is_active is False


class TestAdminFallback:
    def test_fallback_called_when_all_channels_fail(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with patch("src.messaging.router.MessageLog._get_ws", return_value=None):
            from src.messaging.router import MessageRouter
            router = MessageRouter()

        admin_notified = []

        def mock_notify(recipient, event, error):
            admin_notified.append({"event": event})

        router._notify_admin_fallback = mock_notify
        recipient = make_recipient(locale="xx_unknown")
        router.send(recipient, "order_received", {})
        assert len(admin_notified) == 1


class TestTestSend:
    def test_test_send_returns_dict(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        with patch("src.messaging.router.MessageLog._get_ws", return_value=None):
            from src.messaging.router import MessageRouter
            router = MessageRouter()

        result = router.test_send("email", "ko", "order_received", {})
        assert isinstance(result, dict)
        assert "sent" in result

    def test_channels_status_returns_list(self, monkeypatch):
        with patch("src.messaging.router.MessageLog._get_ws", return_value=None):
            from src.messaging.router import MessageRouter
            router = MessageRouter()

        status = router.channels_status()
        assert isinstance(status, list)
        assert len(status) > 0
        assert all("name" in s and "status" in s for s in status)
