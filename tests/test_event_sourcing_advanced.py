"""tests/test_event_sourcing_advanced.py — Phase 77: 이벤트 소싱 고도화 테스트."""
from __future__ import annotations

import pytest

from src.event_sourcing import (
    Event, EventStore, EventBus, Aggregate,
    Snapshot, SnapshotStore, OrderAggregate
)


class TestSnapshot:
    def test_creation(self):
        snap = Snapshot(aggregate_id="order-1", version=5, state={"status": "paid"})
        assert snap.aggregate_id == "order-1"
        assert snap.version == 5
        assert snap.state["status"] == "paid"

    def test_to_dict(self):
        snap = Snapshot(aggregate_id="a1", version=3, state={"x": 1})
        d = snap.to_dict()
        assert d["aggregate_id"] == "a1"
        assert d["version"] == 3
        assert "snapshot_id" in d


class TestSnapshotStore:
    def test_save_and_get_latest(self):
        store = SnapshotStore()
        store.save("agg1", 5, {"status": "v5"})
        store.save("agg1", 10, {"status": "v10"})
        latest = store.get_latest("agg1")
        assert latest is not None
        assert latest.version == 10

    def test_get_all(self):
        store = SnapshotStore()
        store.save("agg1", 1, {})
        store.save("agg1", 2, {})
        snaps = store.get_all("agg1")
        assert len(snaps) == 2

    def test_get_latest_none(self):
        store = SnapshotStore()
        assert store.get_latest("nonexistent") is None

    def test_should_snapshot(self):
        store = SnapshotStore(snapshot_interval=10)
        assert store.should_snapshot(10) is True
        assert store.should_snapshot(5) is False
        assert store.should_snapshot(20) is True
        assert store.should_snapshot(0) is False

    def test_custom_interval(self):
        store = SnapshotStore(snapshot_interval=5)
        assert store.should_snapshot(5) is True
        assert store.should_snapshot(15) is True
        assert store.should_snapshot(7) is False


class TestOrderAggregate:
    def test_create_order(self):
        agg = OrderAggregate("order-001")
        event = agg.create_order("customer-1", [{"sku": "A", "qty": 2}], 50000)
        assert event.event_type == "OrderCreated"
        assert agg.get_status() == "created"
        assert agg.get_version() == 1

    def test_confirm_order(self):
        agg = OrderAggregate("order-001")
        agg.create_order("c1", [], 10000)
        event = agg.confirm_order("PAY-123")
        assert event.event_type == "OrderConfirmed"
        assert agg.get_status() == "confirmed"

    def test_ship_order(self):
        agg = OrderAggregate("order-001")
        agg.create_order("c1", [], 10000)
        agg.confirm_order()
        event = agg.ship_order("TRACK-456")
        assert event.event_type == "OrderShipped"
        assert agg.get_status() == "shipped"

    def test_complete_order(self):
        agg = OrderAggregate("order-001")
        agg.create_order("c1", [], 10000)
        agg.confirm_order()
        agg.ship_order()
        event = agg.complete_order()
        assert event.event_type == "OrderCompleted"
        assert agg.get_status() == "completed"

    def test_cancel_order(self):
        agg = OrderAggregate("order-001")
        agg.create_order("c1", [], 10000)
        event = agg.cancel_order("고객 요청")
        assert event.event_type == "OrderCancelled"
        assert agg.get_status() == "cancelled"

    def test_uncommitted_events(self):
        agg = OrderAggregate("order-001")
        agg.create_order("c1", [], 10000)
        agg.confirm_order()
        uncommitted = agg.get_uncommitted_events()
        assert len(uncommitted) == 2

    def test_mark_events_committed(self):
        agg = OrderAggregate("order-001")
        agg.create_order("c1", [], 10000)
        agg.mark_events_as_committed()
        assert len(agg.get_uncommitted_events()) == 0

    def test_version_increments(self):
        agg = OrderAggregate("order-001")
        agg.create_order("c1", [], 10000)
        assert agg.get_version() == 1
        agg.confirm_order()
        assert agg.get_version() == 2
        agg.ship_order()
        assert agg.get_version() == 3

    def test_load_from_events(self):
        agg = OrderAggregate("order-001")
        events = [
            Event("OrderCreated", "order-001", {"status": "created"}, version=1),
            Event("OrderConfirmed", "order-001", {"status": "confirmed"}, version=2),
        ]
        agg.load_from_events(events)
        assert agg.get_version() == 2
        assert agg.get_status() == "confirmed"


class TestEventStoreIntegration:
    def test_store_order_events(self):
        store = EventStore()
        agg = OrderAggregate("order-002")
        e1 = agg.create_order("c1", [], 20000)
        e2 = agg.confirm_order()
        store.append(e1)
        store.append(e2)
        events = store.get_events("order-002")
        assert len(events) == 2

    def test_snapshot_with_aggregate(self):
        snap_store = SnapshotStore(snapshot_interval=3)
        agg = OrderAggregate("order-003")
        agg.create_order("c1", [], 30000)
        agg.confirm_order()
        agg.ship_order()
        # 3번째 이벤트 — 스냅샷 생성 트리거
        event_count = agg.get_version()
        if snap_store.should_snapshot(event_count):
            snap_store.save(agg.aggregate_id, agg.get_version(), agg.get_state())
        latest = snap_store.get_latest("order-003")
        assert latest is not None
        assert latest.version == 3
