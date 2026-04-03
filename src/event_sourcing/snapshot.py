"""src/event_sourcing/snapshot.py — 스냅샷 관리."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .event import Event


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class Snapshot:
    """애그리거트 스냅샷."""
    aggregate_id: str
    version: int
    state: Dict[str, Any]
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "aggregate_id": self.aggregate_id,
            "version": self.version,
            "state": self.state,
            "created_at": self.created_at,
        }


class SnapshotStore:
    """스냅샷 저장소 (인메모리).

    N개 이벤트마다 자동 스냅샷 생성.
    """

    def __init__(self, snapshot_interval: int = 10) -> None:
        self.snapshot_interval = snapshot_interval
        self._snapshots: Dict[str, List[Snapshot]] = {}

    def save(self, aggregate_id: str, version: int, state: Dict[str, Any]) -> Snapshot:
        snapshot = Snapshot(aggregate_id=aggregate_id, version=version, state=dict(state))
        self._snapshots.setdefault(aggregate_id, []).append(snapshot)
        return snapshot

    def get_latest(self, aggregate_id: str) -> Optional[Snapshot]:
        snaps = self._snapshots.get(aggregate_id)
        if not snaps:
            return None
        return max(snaps, key=lambda s: s.version)

    def get_all(self, aggregate_id: str) -> List[Snapshot]:
        return list(self._snapshots.get(aggregate_id, []))

    def should_snapshot(self, event_count: int) -> bool:
        return event_count > 0 and event_count % self.snapshot_interval == 0
