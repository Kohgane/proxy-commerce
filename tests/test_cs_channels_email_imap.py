from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_email_imap_adapter_inactive_without_keys(monkeypatch):
    monkeypatch.delenv("CS_EMAIL_IMAP_HOST", raising=False)
    monkeypatch.delenv("CS_EMAIL_IMAP_USER", raising=False)
    monkeypatch.delenv("CS_EMAIL_IMAP_PASS", raising=False)
    from src.cs_bot.channels.email_imap import EmailImapAdapter
    adapter = EmailImapAdapter()
    assert not adapter.is_active()
    assert adapter.poll() == []
    assert not adapter.send_reply("test@example.com", "hi")


def test_email_imap_adapter_active_with_keys(monkeypatch):
    monkeypatch.setenv("CS_EMAIL_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("CS_EMAIL_IMAP_USER", "user@example.com")
    monkeypatch.setenv("CS_EMAIL_IMAP_PASS", "secret")
    from importlib import reload
    import src.cs_bot.channels.email_imap as mod
    reload(mod)
    adapter = mod.EmailImapAdapter()
    assert adapter.is_active()


def test_email_imap_poll_imap_error_returns_empty(monkeypatch):
    monkeypatch.setenv("CS_EMAIL_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("CS_EMAIL_IMAP_USER", "user@example.com")
    monkeypatch.setenv("CS_EMAIL_IMAP_PASS", "secret")
    import imaplib
    with patch.object(imaplib, "IMAP4_SSL", side_effect=Exception("connection failed")):
        from src.cs_bot.channels.email_imap import EmailImapAdapter
        adapter = EmailImapAdapter()
        result = adapter.poll()
        assert result == []


def test_email_imap_poll_parses_messages(monkeypatch):
    monkeypatch.setenv("CS_EMAIL_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("CS_EMAIL_IMAP_USER", "user@example.com")
    monkeypatch.setenv("CS_EMAIL_IMAP_PASS", "secret")
    import email as email_mod
    raw_email = b"""From: Test User <test@example.com>\r\nSubject: Question\r\nDate: Mon, 01 Jan 2024 00:00:00 +0000\r\nMessage-ID: <test123>\r\n\r\nHello, I have a question."""
    mock_conn = MagicMock()
    mock_conn.search.return_value = (None, [b"1"])
    mock_conn.fetch.return_value = (None, [(b"1 (RFC822 {100})", raw_email)])
    import imaplib
    with patch.object(imaplib, "IMAP4_SSL", return_value=mock_conn):
        from src.cs_bot.channels.email_imap import EmailImapAdapter
        adapter = EmailImapAdapter()
        msgs = adapter.poll()
        assert len(msgs) == 1
        assert msgs[0].customer_id == "test@example.com"
        assert "question" in msgs[0].body.lower() or "Hello" in msgs[0].body


def test_email_imap_send_reply_resend(monkeypatch):
    monkeypatch.setenv("CS_EMAIL_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("CS_EMAIL_IMAP_USER", "user@example.com")
    monkeypatch.setenv("CS_EMAIL_IMAP_PASS", "secret")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("CS_EMAIL_FROM", "cs@example.com")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_post.return_value = mock_resp
        from src.cs_bot.channels.email_imap import EmailImapAdapter
        adapter = EmailImapAdapter()
        result = adapter.send_reply("customer@example.com", "Hi there!")
        assert result


def test_extract_order_no():
    from src.cs_bot.channels.email_imap import _extract_order_no
    assert _extract_order_no("주문번호: ORDER123456") == "ORDER123456"
    assert _extract_order_no("no order here") == ""
