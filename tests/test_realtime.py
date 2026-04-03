"""tests/test_realtime.py — Phase 67 실시간 대시보드 테스트."""
from __future__ import annotations

import pytest
from src.realtime.realtime_hub import RealtimeHub
from src.realtime.event_stream import EventStream
from src.realtime.dashboard_metrics import DashboardMetrics
from src.realtime.live_notification import LiveNotification
from src.realtime.connection_manager import ConnectionManager


class TestRealtimeHub:
    def test_publish_returns_event_id(self):
        hub = RealtimeHub()
        result = hub.publish("orders", "new_order", {"order_id": "123"})
        assert "event_id" in result
        assert result["channel"] == "orders"

    def test_get_recent_events(self):
        hub = RealtimeHub()
        hub.publish("orders", "new_order", {"id": "1"})
        hub.publish("orders", "cancel", {"id": "2"})
        events = hub.get_recent_events("orders", limit=10)
        assert len(events) == 2

    def test_get_recent_events_limit(self):
        hub = RealtimeHub()
        for i in range(5):
            hub.publish("ch", "evt", {"i": i})
        events = hub.get_recent_events("ch", limit=3)
        assert len(events) == 3

    def test_get_stats(self):
        hub = RealtimeHub()
        hub.publish("ch1", "evt", {})
        hub.publish("ch2", "evt", {})
        stats = hub.get_stats()
        assert stats["total_events"] == 2
        assert stats["active_channels"] == 2

    def test_channel_filter(self):
        hub = RealtimeHub()
        hub.publish("A", "t", {})
        hub.publish("B", "t", {})
        events = hub.get_recent_events("A")
        assert all(e["channel"] == "A" for e in events)


class TestEventStream:
    def test_subscribe_unsubscribe(self):
        stream = EventStream()
        stream.subscribe("ch", "client1")
        assert "client1" in stream.get_subscribers("ch")
        stream.unsubscribe("ch", "client1")
        assert "client1" not in stream.get_subscribers("ch")

    def test_publish_returns_subscriber_count(self):
        stream = EventStream()
        stream.subscribe("ch", "c1")
        stream.subscribe("ch", "c2")
        count = stream.publish("ch", {"msg": "hello"})
        assert count == 2

    def test_publish_empty_channel(self):
        stream = EventStream()
        count = stream.publish("empty", {"msg": "hi"})
        assert count == 0

    def test_get_subscribers_unknown_channel(self):
        stream = EventStream()
        assert stream.get_subscribers("nonexistent") == []


class TestDashboardMetrics:
    def test_collect_returns_dict(self):
        dm = DashboardMetrics()
        result = dm.collect()
        assert isinstance(result, dict)

    def test_collect_has_required_keys(self):
        dm = DashboardMetrics()
        result = dm.collect()
        assert "orders" in result
        assert "revenue" in result
        assert "visitors" in result
        assert "error_rate" in result

    def test_orders_has_subkeys(self):
        dm = DashboardMetrics()
        orders = dm.collect()["orders"]
        assert "count" in orders
        assert "pending" in orders
        assert "processing" in orders

    def test_error_rate_is_float(self):
        dm = DashboardMetrics()
        assert isinstance(dm.collect()["error_rate"], float)


class TestLiveNotification:
    def test_push_returns_notification(self):
        ln = LiveNotification()
        result = ln.push("order_created", {"order_id": "123"})
        assert "notification_id" in result
        assert result["event_type"] == "order_created"

    def test_get_recent(self):
        ln = LiveNotification()
        ln.push("t1", {})
        ln.push("t2", {})
        recent = ln.get_recent(limit=10)
        assert len(recent) == 2

    def test_get_recent_limit(self):
        ln = LiveNotification()
        for i in range(5):
            ln.push("t", {"i": i})
        assert len(ln.get_recent(limit=3)) == 3

    def test_clear(self):
        ln = LiveNotification()
        ln.push("t", {})
        ln.push("t", {})
        count = ln.clear()
        assert count == 2
        assert ln.get_recent() == []


class TestConnectionManager:
    def test_connect(self):
        mgr = ConnectionManager()
        conn = mgr.connect("client1")
        assert conn["client_id"] == "client1"
        assert conn["status"] == "connected"

    def test_disconnect(self):
        mgr = ConnectionManager()
        mgr.connect("c1")
        assert mgr.disconnect("c1") is True
        assert mgr.disconnect("c1") is False

    def test_heartbeat(self):
        mgr = ConnectionManager()
        mgr.connect("c1")
        assert mgr.heartbeat("c1") is True
        assert mgr.heartbeat("unknown") is False

    def test_get_connections(self):
        mgr = ConnectionManager()
        mgr.connect("c1")
        mgr.connect("c2")
        assert len(mgr.get_connections()) == 2

    def test_get_stats(self):
        mgr = ConnectionManager()
        mgr.connect("c1")
        stats = mgr.get_stats()
        assert stats["total_connections"] == 1
