"""tests/test_event_sourcing.py — Phase 64: 이벤트 소싱 테스트."""
from __future__ import annotations

import pytest

from src.event_sourcing import (
    Event, EventStore, EventHandler, EventBus,
    Aggregate, EventProjection, EventReplay,
)


class TestEvent:
    def test_event_creation(self):
        event = Event(event_type="OrderCreated", aggregate_id="order-1", data={"amount": 100})
        assert event.event_type == "OrderCreated"
        assert event.aggregate_id == "order-1"
        assert "event_id" in event.to_dict()

    def test_to_dict(self):
        event = Event(event_type="Test", aggregate_id="agg-1", data={})
        d = event.to_dict()
        assert all(k in d for k in ["event_id", "event_type", "aggregate_id", "timestamp"])


class TestEventStore:
    def test_append_and_get_all(self):
        store = EventStore()
        event = Event(event_type="E1", aggregate_id="a1", data={})
        store.append(event)
        assert len(store.get_all()) == 1

    def test_get_events_by_aggregate(self):
        store = EventStore()
        store.append(Event("E1", "agg-1", {}))
        store.append(Event("E2", "agg-2", {}))
        store.append(Event("E3", "agg-1", {}))
        events = store.get_events("agg-1")
        assert len(events) == 2

    def test_get_since(self):
        store = EventStore()
        e1 = Event("E1", "a1", {})
        store.append(e1)
        since = store.get_since(e1.timestamp)
        assert len(since) >= 1


class TestEventBus:
    def test_subscribe_and_publish(self):
        received = []

        class Handler:
            def handle(self, event):
                received.append(event)

        bus = EventBus()
        bus.subscribe("OrderCreated", Handler())
        event = Event("OrderCreated", "o1", {})
        bus.publish(event)
        assert len(received) == 1

    def test_no_handler_no_error(self):
        bus = EventBus()
        event = Event("Unknown", "x1", {})
        bus.publish(event)  # should not raise


class TestAggregate:
    def test_load_from_events(self):
        agg = Aggregate("order-1")
        events = [
            Event("OrderCreated", "order-1", {"status": "created"}, version=1),
            Event("OrderPaid", "order-1", {"status": "paid"}, version=2),
        ]
        agg.load_from_events(events)
        assert agg.get_version() == 2
        assert agg.get_state()["status"] == "paid"


class TestEventProjection:
    def test_project(self):
        projection = EventProjection()
        events = [
            Event("Created", "agg-1", {"name": "Test"}),
            Event("Updated", "agg-1", {"name": "New"}),
        ]
        result = projection.project(events)
        assert "agg-1" in result
        assert result["agg-1"]["name"] == "New"


class TestEventReplay:
    def test_replay_until_version(self):
        replay = EventReplay()
        events = [
            Event("E1", "a1", {}, version=1),
            Event("E2", "a1", {}, version=2),
            Event("E3", "a1", {}, version=3),
        ]
        replayed = replay.replay_until_version(events, until_version=2)
        assert len(replayed) == 2

    def test_replay_full(self):
        replay = EventReplay()
        events = [Event("E1", "a1", {}, version=1)]
        replayed = replay.replay(events)
        assert len(replayed) == 1
