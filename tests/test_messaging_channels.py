"""tests/test_messaging_channels.py — 채널 어댑터 테스트 (Phase 134)."""
import os
import pytest
from unittest.mock import MagicMock, patch


def make_recipient(**kwargs):
    from src.messaging.models import Recipient
    defaults = {"name": "테스터", "locale": "ko"}
    defaults.update(kwargs)
    return Recipient(**defaults)


class TestResendChannel:
    def test_is_active_when_key_set(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_test")
        from src.messaging.channels.email_channel import ResendChannel
        ch = ResendChannel()
        assert ch.is_active is True

    def test_is_inactive_when_no_key(self, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        from src.messaging.channels.email_channel import ResendChannel
        ch = ResendChannel()
        assert ch.is_active is False

    def test_send_returns_no_email_error(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_test")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        from src.messaging.channels.email_channel import ResendChannel
        ch = ResendChannel()
        r = make_recipient()  # no email
        result = ch.send(r, "안녕하세요", {})
        assert result.sent is False
        assert result.error == "no_email"

    def test_dry_run_returns_dry_run_error(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.messaging.channels.email_channel import ResendChannel
        ch = ResendChannel()
        r = make_recipient(email="test@example.com")
        result = ch.send(r, "테스트", {})
        assert result.sent is False
        assert result.error == "dry_run"

    def test_health_check_structure(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_test")
        from src.messaging.channels.email_channel import ResendChannel
        ch = ResendChannel()
        h = ch.health_check()
        assert h["name"] == "email"
        assert h["status"] in ("ok", "missing_key")


class TestTelegramNotifyChannel:
    def test_is_active_when_keys_set(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot123")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat456")
        from src.messaging.channels.telegram_channel import TelegramNotifyChannel
        ch = TelegramNotifyChannel()
        assert ch.is_active is True

    def test_is_inactive_when_no_token(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        from src.messaging.channels.telegram_channel import TelegramNotifyChannel
        ch = TelegramNotifyChannel()
        assert ch.is_active is False

    def test_dry_run(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        from src.messaging.channels.telegram_channel import TelegramNotifyChannel
        ch = TelegramNotifyChannel()
        r = make_recipient(telegram_chat_id="123")
        result = ch.send(r, "테스트", {})
        assert result.sent is False
        assert result.error == "dry_run"


class TestKakaoAlimtalkChannel:
    def test_is_inactive_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("KAKAO_ALIMTALK_API_KEY", raising=False)
        from src.messaging.channels.kakao_channel import KakaoAlimtalkChannel
        ch = KakaoAlimtalkChannel()
        assert ch.is_active is False

    def test_is_active_when_keys_set(self, monkeypatch):
        monkeypatch.setenv("KAKAO_ALIMTALK_API_KEY", "ka_key")
        monkeypatch.setenv("KAKAO_ALIMTALK_SENDER_KEY", "ka_sender")
        from src.messaging.channels.kakao_channel import KakaoAlimtalkChannel
        ch = KakaoAlimtalkChannel()
        assert ch.is_active is True

    def test_returns_not_configured_when_inactive(self, monkeypatch):
        monkeypatch.delenv("KAKAO_ALIMTALK_API_KEY", raising=False)
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        from src.messaging.channels.kakao_channel import KakaoAlimtalkChannel
        ch = KakaoAlimtalkChannel()
        r = make_recipient(phone_e164="+821012345678")
        result = ch.send(r, "테스트", {})
        assert result.sent is False
        assert result.error == "not_configured"


class TestLineChannels:
    def test_notify_inactive_no_token(self, monkeypatch):
        monkeypatch.delenv("LINE_NOTIFY_TOKEN", raising=False)
        from src.messaging.channels.line_channel import LineNotifyChannel
        ch = LineNotifyChannel()
        assert ch.is_active is False

    def test_messaging_inactive_no_token(self, monkeypatch):
        monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
        from src.messaging.channels.line_channel import LineMessagingChannel
        ch = LineMessagingChannel()
        assert ch.is_active is False

    def test_messaging_requires_line_user_id(self, monkeypatch):
        monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "tok")
        monkeypatch.setenv("LINE_CHANNEL_SECRET", "sec")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        from src.messaging.channels.line_channel import LineMessagingChannel
        ch = LineMessagingChannel()
        r = make_recipient()  # no line_user_id
        result = ch.send(r, "テスト", {})
        assert result.sent is False
        assert result.error == "no_line_user_id"


class TestWhatsAppChannel:
    def test_is_inactive_no_keys(self, monkeypatch):
        monkeypatch.delenv("META_WHATSAPP_TOKEN", raising=False)
        from src.messaging.channels.whatsapp_channel import WhatsAppChannel
        ch = WhatsAppChannel()
        assert ch.is_active is False

    def test_requires_phone(self, monkeypatch):
        monkeypatch.setenv("META_WHATSAPP_TOKEN", "wa_tok")
        monkeypatch.setenv("META_WHATSAPP_PHONE_ID", "12345")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        from src.messaging.channels.whatsapp_channel import WhatsAppChannel
        ch = WhatsAppChannel()
        r = make_recipient()  # no phone
        result = ch.send(r, "Hello", {})
        assert result.sent is False
        assert result.error == "no_phone"


class TestSMSChannel:
    def test_inactive_no_keys(self, monkeypatch):
        for key in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM",
                    "ALIGO_API_KEY", "ALIGO_USER_ID", "ALIGO_SENDER"]:
            monkeypatch.delenv(key, raising=False)
        from src.messaging.channels.sms_channel import SMSChannel
        ch = SMSChannel()
        assert ch.is_active is False

    def test_active_with_twilio(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "auth")
        monkeypatch.setenv("TWILIO_FROM", "+15005551234")
        from src.messaging.channels.sms_channel import SMSChannel
        ch = SMSChannel()
        assert ch.is_active is True

    def test_active_with_aligo(self, monkeypatch):
        monkeypatch.setenv("ALIGO_API_KEY", "aligo_key")
        monkeypatch.setenv("ALIGO_USER_ID", "aligo_user")
        monkeypatch.setenv("ALIGO_SENDER", "01012345678")
        from src.messaging.channels.sms_channel import SMSChannel
        ch = SMSChannel()
        assert ch.is_active is True

    def test_no_phone_returns_error(self, monkeypatch):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "auth")
        monkeypatch.setenv("TWILIO_FROM", "+15005551234")
        monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
        from src.messaging.channels.sms_channel import SMSChannel
        ch = SMSChannel()
        r = make_recipient()  # no phone
        result = ch.send(r, "테스트", {})
        assert result.sent is False
        assert result.error == "no_phone"


class TestDiscordChannel:
    def test_inactive_no_webhook(self, monkeypatch):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        from src.messaging.channels.discord_channel import DiscordChannel
        ch = DiscordChannel()
        assert ch.is_active is False

    def test_active_with_webhook(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/abc")
        from src.messaging.channels.discord_channel import DiscordChannel
        ch = DiscordChannel()
        assert ch.is_active is True

    def test_dry_run(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/abc")
        from src.messaging.channels.discord_channel import DiscordChannel
        ch = DiscordChannel()
        r = make_recipient()
        result = ch.send(r, "테스트", {})
        assert result.sent is False
        assert result.error == "dry_run"


class TestSendResult:
    def test_to_dict(self):
        from src.messaging.models import SendResult
        r = SendResult(sent=True, channel="email", provider_msg_id="msg123")
        d = r.to_dict()
        assert d["sent"] is True
        assert d["channel"] == "email"
        assert d["provider_msg_id"] == "msg123"
        assert d["error"] is None
