"""tests/test_email_service.py — Phase 56: 이메일 서비스 테스트."""
from __future__ import annotations

import pytest
from src.email_service.email_provider import EmailProvider
from src.email_service.smtp_provider import SMTPProvider
from src.email_service.sendgrid_provider import SendGridProvider
from src.email_service.email_template import EmailTemplate
from src.email_service.email_queue import EmailQueue
from src.email_service.email_tracker import EmailTracker


class TestSMTPProvider:
    def setup_method(self):
        self.provider = SMTPProvider()

    def test_is_email_provider(self):
        assert isinstance(self.provider, EmailProvider)

    def test_send_returns_result(self):
        result = self.provider.send("user@example.com", "제목", "본문")
        assert result["status"] == "sent"
        assert result["to"] == "user@example.com"
        assert result["email_id"]

    def test_send_records_history(self):
        self.provider.send("a@b.com", "s", "b")
        self.provider.send("c@d.com", "s2", "b2")
        assert len(self.provider.get_sent()) == 2


class TestSendGridProvider:
    def setup_method(self):
        self.provider = SendGridProvider(api_key="test-key")

    def test_is_email_provider(self):
        assert isinstance(self.provider, EmailProvider)

    def test_send(self):
        result = self.provider.send("user@example.com", "Hello", "Body")
        assert result["provider"] == "sendgrid"
        assert result["status"] == "sent"


class TestEmailTemplate:
    def test_get_builtin_order_confirm(self):
        tmpl = EmailTemplate.get_builtin("order_confirm")
        assert tmpl.name == "order_confirm"

    def test_render(self):
        tmpl = EmailTemplate.get_builtin("order_confirm")
        subject, body = tmpl.render({"order_id": "ORD-001", "name": "홍길동", "total": "50000"})
        assert "ORD-001" in subject
        assert "홍길동" in body

    def test_list_builtins(self):
        builtins = EmailTemplate.list_builtins()
        assert "order_confirm" in builtins
        assert "shipping_notify" in builtins
        assert "password_reset" in builtins

    def test_missing_builtin(self):
        with pytest.raises(KeyError):
            EmailTemplate.get_builtin("nonexistent_template")

    def test_custom_template(self):
        tmpl = EmailTemplate("custom", "Hello {name}", "Dear {name},\n{message}")
        subject, body = tmpl.render({"name": "Alice", "message": "Welcome!"})
        assert subject == "Hello Alice"
        assert "Alice" in body


class TestEmailQueue:
    def setup_method(self):
        self.queue = EmailQueue()
        self.provider = SMTPProvider()

    def test_enqueue_returns_email_id(self):
        email_id = self.queue.enqueue("user@example.com", "order_confirm",
                                      {"order_id": "1", "name": "홍", "total": "0"})
        assert email_id

    def test_process_queue(self):
        self.queue.enqueue("a@b.com", "order_confirm",
                           {"order_id": "1", "name": "홍", "total": "0"})
        results = self.queue.process_queue(self.provider)
        assert results[0]["status"] == "sent"
        assert len(self.queue.get_pending()) == 0

    def test_failed_on_bad_template(self):
        queue = EmailQueue(max_retries=1)
        queue.enqueue("a@b.com", "nonexistent_template", {})
        queue.process_queue(self.provider)
        assert len(queue.get_failed()) == 1

    def test_retry_failed(self):
        queue = EmailQueue(max_retries=1)
        queue.enqueue("a@b.com", "nonexistent_template", {})
        queue.process_queue(self.provider)
        assert len(queue.get_failed()) == 1
        # Re-add good email to retry
        queue._failed[0]["template_name"] = "order_confirm"
        queue._failed[0]["context"] = {"order_id": "1", "name": "홍", "total": "0"}
        results = queue.retry_failed(self.provider)
        # Should attempt and either succeed or fail


class TestEmailTracker:
    def setup_method(self):
        self.tracker = EmailTracker()

    def test_record_sent(self):
        self.tracker.record_sent("e1", "a@b.com", "Hello")
        history = self.tracker.get_history()
        assert len(history) == 1
        assert history[0]["email_id"] == "e1"

    def test_record_open(self):
        self.tracker.record_sent("e1", "a@b.com", "Hello")
        self.tracker.record_open("e1")
        history = self.tracker.get_history()
        assert history[0]["opened"] is True
        assert history[0]["open_count"] == 1

    def test_record_click(self):
        self.tracker.record_sent("e1", "a@b.com", "Hello")
        self.tracker.record_click("e1", "https://example.com")
        history = self.tracker.get_history()
        assert len(history[0]["clicks"]) == 1

    def test_get_stats(self):
        self.tracker.record_sent("e1", "a@b.com", "S1")
        self.tracker.record_sent("e2", "b@c.com", "S2")
        self.tracker.record_open("e1")
        stats = self.tracker.get_stats()
        assert stats["total_sent"] == 2
        assert stats["total_opened"] == 1
        assert stats["open_rate"] == 50.0
