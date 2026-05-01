"""tests/test_week1_monitoring.py — Tests for ProductWatcher and Notifier."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from monitoring.notifier import (
    Notifier,
    SlackBackend,
    TelegramBackend,
    _format_event,
    _post_json,
)
from monitoring.watcher import ChangeEvent, ProductWatcher


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _product(cost_price=100.0, sell_price=None, stock_status="in_stock", pid="P-001"):
    p = MagicMock()
    p.source = "test"
    p.source_product_id = pid
    p.cost_price = cost_price
    p.sell_price = sell_price
    p.stock_status = stock_status
    p.title = "Test Product"
    return p


# ---------------------------------------------------------------------------
# ProductWatcher tests
# ---------------------------------------------------------------------------

class TestProductWatcher:
    def test_first_check_no_events(self, tmp_path):
        watcher = ProductWatcher(state_path=tmp_path / "state.json")
        events = watcher.check(_product())
        assert events == []

    def test_price_change_detected(self, tmp_path):
        watcher = ProductWatcher(state_path=tmp_path / "state.json")
        p1 = _product(cost_price=100.0)
        watcher.check(p1)

        p2 = _product(cost_price=120.0)
        events = watcher.check(p2)
        assert len(events) == 1
        assert events[0].field == "cost_price"
        assert events[0].old_value == 100.0
        assert events[0].new_value == 120.0

    def test_stock_change_detected(self, tmp_path):
        watcher = ProductWatcher(state_path=tmp_path / "state.json")
        watcher.check(_product(stock_status="in_stock"))
        events = watcher.check(_product(stock_status="out_of_stock"))
        assert any(e.field == "stock_status" for e in events)

    def test_no_change_no_events(self, tmp_path):
        watcher = ProductWatcher(state_path=tmp_path / "state.json")
        p = _product(cost_price=100.0, stock_status="in_stock")
        watcher.check(p)
        events = watcher.check(_product(cost_price=100.0, stock_status="in_stock"))
        assert events == []

    def test_state_persisted_to_disk(self, tmp_path):
        state_file = tmp_path / "state.json"
        watcher = ProductWatcher(state_path=state_file)
        watcher.check(_product(cost_price=50.0))
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert "test:P-001" in data

    def test_reload_state_from_disk(self, tmp_path):
        state_file = tmp_path / "state.json"
        # First session
        watcher1 = ProductWatcher(state_path=state_file)
        watcher1.check(_product(cost_price=100.0))

        # Second session — should detect change
        watcher2 = ProductWatcher(state_path=state_file)
        events = watcher2.check(_product(cost_price=200.0))
        assert len(events) == 1

    def test_reset_clears_snapshot(self, tmp_path):
        watcher = ProductWatcher(state_path=tmp_path / "state.json")
        p = _product(cost_price=100.0)
        watcher.check(p)
        watcher.reset(p)
        # After reset, next check should not produce change events
        events = watcher.check(_product(cost_price=999.0))
        assert events == []

    def test_check_batch(self, tmp_path):
        watcher = ProductWatcher(state_path=tmp_path / "state.json")
        products = [_product(cost_price=10.0, pid="P-001"), _product(cost_price=20.0, pid="P-002")]
        # First check — baseline
        watcher.check_batch(products)
        # Second check with changed prices
        changed = [_product(cost_price=15.0, pid="P-001"), _product(cost_price=25.0, pid="P-002")]
        events = watcher.check_batch(changed)
        assert len(events) == 2

    def test_change_event_str(self):
        event = ChangeEvent(
            source="test",
            source_product_id="P-001",
            field="cost_price",
            old_value=100.0,
            new_value=120.0,
            title="Fancy Legging",
        )
        text = str(event)
        assert "cost_price" in text
        assert "100.0" in text
        assert "120.0" in text


# ---------------------------------------------------------------------------
# Notifier / backends tests
# ---------------------------------------------------------------------------

class TestNotifier:
    def test_format_event_contains_key_info(self):
        event = ChangeEvent("alo", "P-001", "cost_price", 100.0, 120.0, "Legging")
        text = _format_event(event)
        assert "alo" in text
        assert "Legging" in text
        assert "100.0" in text or "100" in text

    def test_notify_calls_backend(self):
        backend = MagicMock()
        notifier = Notifier([backend])
        event = ChangeEvent("alo", "P-001", "stock_status", "in_stock", "out_of_stock", "Legging")
        notifier.notify(event)
        backend.send.assert_called_once()

    def test_notify_batch(self):
        backend = MagicMock()
        notifier = Notifier([backend])
        events = [
            ChangeEvent("alo", "P-001", "cost_price", 100.0, 110.0),
            ChangeEvent("lululemon", "P-002", "stock_status", "in_stock", "out_of_stock"),
        ]
        notifier.notify_batch(events)
        assert backend.send.call_count == 2

    def test_no_backend_does_not_raise(self):
        notifier = Notifier([])
        event = ChangeEvent("test", "P-001", "cost_price", 10.0, 20.0)
        notifier.notify(event)  # should not raise

    def test_backend_failure_does_not_propagate(self):
        backend = MagicMock()
        backend.send.side_effect = RuntimeError("network down")
        notifier = Notifier([backend])
        event = ChangeEvent("test", "P-001", "cost_price", 10.0, 20.0)
        notifier.notify(event)  # should not raise

    def test_from_env_no_config(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
        notifier = Notifier.from_env()
        assert isinstance(notifier, Notifier)

    def test_from_env_telegram(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
        notifier = Notifier.from_env()
        assert any(isinstance(b, TelegramBackend) for b in notifier._backends)

    def test_from_env_slack(self, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/fake")
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        notifier = Notifier.from_env()
        assert any(isinstance(b, SlackBackend) for b in notifier._backends)

    def test_telegram_backend_empty_token_raises(self):
        with pytest.raises(ValueError):
            TelegramBackend(token="", chat_id="123")

    def test_slack_backend_empty_url_raises(self):
        with pytest.raises(ValueError):
            SlackBackend(webhook_url="")

    def test_telegram_send(self, monkeypatch):
        calls = []

        def fake_post(url, payload, timeout=10):
            calls.append((url, payload))
            return {"ok": True}

        monkeypatch.setattr("monitoring.notifier._post_json", fake_post)
        backend = TelegramBackend(token="TOKEN", chat_id="CHAT")
        backend.send("hello")
        assert len(calls) == 1
        assert "TOKEN" in calls[0][0]

    def test_slack_send(self, monkeypatch):
        calls = []

        def fake_post(url, payload, timeout=10):
            calls.append((url, payload))
            return {}

        monkeypatch.setattr("monitoring.notifier._post_json", fake_post)
        backend = SlackBackend(webhook_url="https://hooks.slack.com/services/X")
        backend.send("hello")
        assert len(calls) == 1
        assert calls[0][1] == {"text": "hello"}
