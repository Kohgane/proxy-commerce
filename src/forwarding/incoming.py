"""src/forwarding/incoming.py — 배송대행지 입고 확인 자동화 (Phase 102)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class IncomingStatus(Enum):
    WAITING = 'waiting'
    RECEIVED = 'received'
    INSPECTED = 'inspected'
    READY_TO_SHIP = 'ready_to_ship'
    ISSUE_FOUND = 'issue_found'


@dataclass
class IncomingRecord:
    """입고 기록."""

    record_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    order_id: str = ''
    agent_id: str = ''
    tracking_number: str = ''
    status: IncomingStatus = IncomingStatus.WAITING
    received_at: Optional[datetime] = None
    weight_kg: float = 0.0
    photo_urls: List[str] = field(default_factory=list)
    inspection_notes: str = ''
    issue_type: Optional[str] = None  # 'damaged' | 'quantity_mismatch' | 'wrong_item' | None
    metadata: Dict = field(default_factory=dict)


class IncomingVerifier:
    """배송대행지 입고 확인 서비스."""

    def __init__(self) -> None:
        self._records: Dict[str, IncomingRecord] = {}

    def verify(
        self,
        order_id: str,
        tracking_number: str,
        agent_id: str,
    ) -> IncomingRecord:
        """입고 확인: 기존 기록을 조회하거나 새로 생성 후 에이전트에서 상태를 폴링한다."""
        # 기존 기록 검색
        for record in self._records.values():
            if record.tracking_number == tracking_number and record.agent_id == agent_id:
                return self._refresh_from_agent(record)

        record = IncomingRecord(
            order_id=order_id,
            agent_id=agent_id,
            tracking_number=tracking_number,
        )
        record = self._refresh_from_agent(record)
        self._records[record.record_id] = record
        return record

    def _refresh_from_agent(self, record: IncomingRecord) -> IncomingRecord:
        """에이전트에서 최신 입고 상태를 조회해 기록을 업데이트한다."""
        try:
            from .agent import ForwardingAgentManager
            mgr = ForwardingAgentManager()
            agent = mgr.get_agent(record.agent_id)
            data = agent.check_incoming(record.tracking_number)

            status_map = {
                'waiting': IncomingStatus.WAITING,
                'received': IncomingStatus.RECEIVED,
                'inspected': IncomingStatus.INSPECTED,
                'ready_to_ship': IncomingStatus.READY_TO_SHIP,
                'issue_found': IncomingStatus.ISSUE_FOUND,
            }
            raw_status = data.get('status', 'waiting')
            record.status = status_map.get(raw_status, IncomingStatus.WAITING)

            if data.get('received_at'):
                try:
                    record.received_at = datetime.fromisoformat(data['received_at'])
                except ValueError:
                    record.received_at = datetime.now(timezone.utc)
            elif record.status != IncomingStatus.WAITING:
                record.received_at = datetime.now(timezone.utc)

            record.weight_kg = float(data.get('weight_kg', record.weight_kg))
            record.photo_urls = list(data.get('photo_urls', record.photo_urls))
            record.inspection_notes = data.get('inspection_notes', record.inspection_notes)
            record.issue_type = data.get('issue_type', record.issue_type)

            self._notify(record)
        except Exception as exc:
            logger.warning("에이전트 입고 조회 실패 (%s): %s", record.tracking_number, exc)
        return record

    def check_status(self, record_id: str) -> IncomingRecord:
        """특정 입고 기록의 상태를 갱신해 반환한다."""
        if record_id not in self._records:
            raise KeyError(f"입고 기록 없음: {record_id}")
        record = self._records[record_id]
        return self._refresh_from_agent(record)

    def list_records(
        self, status: Optional[IncomingStatus] = None
    ) -> List[IncomingRecord]:
        """입고 기록 목록을 반환한다."""
        records = list(self._records.values())
        if status is not None:
            records = [r for r in records if r.status == status]
        return records

    def process_inspection(
        self,
        record_id: str,
        passed: bool,
        notes: str = '',
        issue_type: Optional[str] = None,
    ) -> IncomingRecord:
        """검수 결과를 처리한다."""
        if record_id not in self._records:
            raise KeyError(f"입고 기록 없음: {record_id}")
        record = self._records[record_id]
        record.inspection_notes = notes
        if passed:
            record.status = IncomingStatus.READY_TO_SHIP
            record.issue_type = None
        else:
            record.status = IncomingStatus.ISSUE_FOUND
            record.issue_type = issue_type
        self._notify(record)
        return record

    def _notify(self, record: IncomingRecord) -> None:
        """알림을 발송한다 (실패 시 무시)."""
        try:
            from ..notification_hub import NotificationHub
            hub = NotificationHub()
            hub.send(
                event='incoming_updated',
                data={
                    'record_id': record.record_id,
                    'order_id': record.order_id,
                    'status': record.status.value,
                    'tracking_number': record.tracking_number,
                },
            )
        except Exception:
            pass

    def get_stats(self) -> Dict:
        """상태별 통계를 반환한다."""
        stats: Dict[str, int] = {s.value: 0 for s in IncomingStatus}
        for record in self._records.values():
            stats[record.status.value] += 1
        return stats
