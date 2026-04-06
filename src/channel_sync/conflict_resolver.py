"""src/channel_sync/conflict_resolver.py — 동시 수정 충돌 해결 (Phase 109).

SyncConflictResolver: 소싱처 vs 판매채널 데이터 충돌 해결 + 로그 기록
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ConflictStrategy(str, Enum):
    source_priority = 'source_priority'    # 소싱처 우선
    channel_priority = 'channel_priority'  # 판매채널 우선
    latest_wins = 'latest_wins'            # 최신 우선
    manual = 'manual'                      # 수동 확인


class ConflictStatus(str, Enum):
    unresolved = 'unresolved'
    resolved = 'resolved'
    pending_manual = 'pending_manual'


@dataclass
class Conflict:
    conflict_id: str
    product_id: str
    field_name: str
    source_value: object
    channel_value: object
    channel: str
    strategy: ConflictStrategy
    status: ConflictStatus = ConflictStatus.unresolved
    resolved_value: object = None
    resolved_at: Optional[str] = None
    resolution_note: str = ''
    detected_at: str = ''

    def __post_init__(self):
        if not self.detected_at:
            self.detected_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'conflict_id': self.conflict_id,
            'product_id': self.product_id,
            'field_name': self.field_name,
            'source_value': self.source_value,
            'channel_value': self.channel_value,
            'channel': self.channel,
            'strategy': self.strategy.value if hasattr(self.strategy, 'value') else self.strategy,
            'status': self.status.value if hasattr(self.status, 'value') else self.status,
            'resolved_value': self.resolved_value,
            'resolved_at': self.resolved_at,
            'resolution_note': self.resolution_note,
            'detected_at': self.detected_at,
        }


class SyncConflictResolver:
    """동기화 충돌 해결기."""

    def __init__(self, default_strategy: ConflictStrategy = ConflictStrategy.source_priority):
        self._default_strategy = default_strategy
        self._conflicts: Dict[str, Conflict] = {}

    # ── 충돌 감지 / 해결 ─────────────────────────────────────────────────────

    def detect_conflicts(
        self,
        product_id: str,
        source_data: dict,
        channel_data: dict,
        channel: str,
    ) -> List[Conflict]:
        """두 데이터셋 간 충돌 감지."""
        conflicts = []
        compare_fields = {'price', 'title', 'stock', 'description', 'category'}

        for field_name in compare_fields:
            source_val = source_data.get(field_name)
            channel_val = channel_data.get(field_name)
            if source_val is not None and channel_val is not None and source_val != channel_val:
                conflict = Conflict(
                    conflict_id=str(uuid.uuid4()),
                    product_id=product_id,
                    field_name=field_name,
                    source_value=source_val,
                    channel_value=channel_val,
                    channel=channel,
                    strategy=self._default_strategy,
                )
                self._conflicts[conflict.conflict_id] = conflict
                conflicts.append(conflict)

        return conflicts

    def resolve(
        self,
        source_data: dict,
        channel_data: dict,
        strategy: Optional[ConflictStrategy] = None,
    ) -> dict:
        """충돌 해결 — 전략에 따라 최종 데이터 반환."""
        used_strategy = strategy or self._default_strategy

        if used_strategy == ConflictStrategy.source_priority:
            result = dict(channel_data)
            result.update(source_data)
            return result

        if used_strategy == ConflictStrategy.channel_priority:
            result = dict(source_data)
            result.update(channel_data)
            return result

        if used_strategy == ConflictStrategy.latest_wins:
            source_ts = source_data.get('updated_at', '')
            channel_ts = channel_data.get('updated_at', '')
            if source_ts >= channel_ts:
                result = dict(channel_data)
                result.update(source_data)
            else:
                result = dict(source_data)
                result.update(channel_data)
            return result

        # manual — 소싱처 우선 + pending_manual 마킹
        result = dict(channel_data)
        result.update(source_data)
        result['_manual_review_required'] = True
        return result

    def resolve_conflict(
        self,
        conflict_id: str,
        resolved_value: object,
        resolution_note: str = '',
    ) -> Optional[Conflict]:
        """특정 충돌 수동 해결."""
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            return None
        conflict.status = ConflictStatus.resolved
        conflict.resolved_value = resolved_value
        conflict.resolved_at = datetime.now(tz=timezone.utc).isoformat()
        conflict.resolution_note = resolution_note
        logger.info("충돌 수동 해결: %s", conflict_id)
        return conflict

    # ── 조회 ─────────────────────────────────────────────────────────────────

    def get_unresolved_conflicts(self) -> List[Conflict]:
        """미해결 충돌 목록."""
        return [c for c in self._conflicts.values() if c.status == ConflictStatus.unresolved]

    def get_all_conflicts(self) -> List[Conflict]:
        """전체 충돌 목록."""
        return list(self._conflicts.values())

    def get_conflict(self, conflict_id: str) -> Optional[Conflict]:
        """특정 충돌 조회."""
        return self._conflicts.get(conflict_id)

    def get_stats(self) -> dict:
        """충돌 통계."""
        conflicts = list(self._conflicts.values())
        by_status: Dict[str, int] = {}
        by_channel: Dict[str, int] = {}
        for c in conflicts:
            status_val = c.status.value if hasattr(c.status, 'value') else str(c.status)
            by_status[status_val] = by_status.get(status_val, 0) + 1
            by_channel[c.channel] = by_channel.get(c.channel, 0) + 1
        return {
            'total': len(conflicts),
            'by_status': by_status,
            'by_channel': by_channel,
            'unresolved': sum(1 for c in conflicts if c.status == ConflictStatus.unresolved),
        }
