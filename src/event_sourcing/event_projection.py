"""src/event_sourcing/event_projection.py — 이벤트 프로젝션."""
from __future__ import annotations

from typing import Dict, List

from .event import Event


class EventProjection:
    """이벤트를 읽기 모델 dict으로 변환."""

    def project(self, events: List[Event]) -> Dict[str, dict]:
        result: Dict[str, dict] = {}
        for event in events:
            agg_id = event.aggregate_id
            if agg_id not in result:
                result[agg_id] = {"aggregate_id": agg_id, "events": [], "version": 0}
            result[agg_id]["events"].append(event.event_type)
            result[agg_id]["version"] = max(result[agg_id]["version"], event.version)
            result[agg_id].update(event.data)
        return result
