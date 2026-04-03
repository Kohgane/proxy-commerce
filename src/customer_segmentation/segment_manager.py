"""세그먼트 CRUD 관리자."""
from __future__ import annotations
import uuid
from .models import Segment

class SegmentManager:
    def __init__(self) -> None:
        self._segments: dict[str, Segment] = {}

    def create(self, name: str, description: str = "", rules: list[dict] | None = None) -> Segment:
        seg = Segment(
            segment_id=str(uuid.uuid4()),
            name=name,
            description=description,
            rules=rules or [],
        )
        self._segments[seg.segment_id] = seg
        return seg

    def get(self, segment_id: str) -> Segment | None:
        return self._segments.get(segment_id)

    def list(self) -> list[Segment]:
        return list(self._segments.values())

    def update(self, segment_id: str, **kwargs) -> Segment | None:
        seg = self._segments.get(segment_id)
        if not seg:
            return None
        for k, v in kwargs.items():
            setattr(seg, k, v)
        return seg

    def delete(self, segment_id: str) -> bool:
        return bool(self._segments.pop(segment_id, None))
