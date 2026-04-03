"""src/event_sourcing/__init__.py — Phase 64/77: 이벤트 소싱."""
from __future__ import annotations

from .event import Event
from .event_store import EventStore
from .event_handler import EventHandler
from .event_bus import EventBus
from .aggregate import Aggregate
from .event_projection import EventProjection
from .event_replay import EventReplay
from .snapshot import Snapshot, SnapshotStore
from .order_aggregate import OrderAggregate

__all__ = [
    "Event",
    "EventStore",
    "EventHandler",
    "EventBus",
    "Aggregate",
    "EventProjection",
    "EventReplay",
    "Snapshot",
    "SnapshotStore",
    "OrderAggregate",
]
