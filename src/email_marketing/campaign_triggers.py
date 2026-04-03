"""캠페인 트리거 ABC 및 구현체."""
from __future__ import annotations
from abc import ABC, abstractmethod

class CampaignTrigger(ABC):
    @abstractmethod
    def should_trigger(self, context: dict) -> bool: ...
    @abstractmethod
    def trigger_type(self) -> str: ...

class ScheduleTrigger(CampaignTrigger):
    def __init__(self, scheduled_at: str) -> None:
        self._scheduled_at = scheduled_at

    def trigger_type(self) -> str:
        return "schedule"

    def should_trigger(self, context: dict) -> bool:
        now = context.get("now", "")
        return now >= self._scheduled_at

class EventTrigger(CampaignTrigger):
    def __init__(self, event_type: str) -> None:
        self._event_type = event_type

    def trigger_type(self) -> str:
        return "event"

    def should_trigger(self, context: dict) -> bool:
        return context.get("event") == self._event_type

class SegmentTrigger(CampaignTrigger):
    def __init__(self, segment_id: str) -> None:
        self._segment_id = segment_id

    def trigger_type(self) -> str:
        return "segment"

    def should_trigger(self, context: dict) -> bool:
        return self._segment_id in context.get("segments", [])
