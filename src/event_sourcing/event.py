"""src/event_sourcing/event.py — 이벤트 데이터클래스."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class Event:
    event_type: str
    aggregate_id: str
    data: Dict[str, Any]
    timestamp: str = field(default_factory=_now_iso)
    version: int = 1
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "data": self.data,
            "timestamp": self.timestamp,
            "version": self.version,
        }
