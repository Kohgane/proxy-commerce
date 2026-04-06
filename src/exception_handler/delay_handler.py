"""src/exception_handler/delay_handler.py — 배송 지연 대응 (Phase 105)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DelayStage(str, Enum):
    minor = 'minor'        # 1~2일
    moderate = 'moderate'  # 3~5일
    severe = 'severe'      # 5일+


class DelayAction(str, Enum):
    notify_customer = 'notify_customer'
    query_carrier = 'query_carrier'
    offer_compensation = 'offer_compensation'
    reship_or_refund = 'reship_or_refund'


@dataclass
class DelayRecord:
    record_id: str
    order_id: str
    expected_date: str
    current_date: str
    delay_days: float
    stage: DelayStage
    actions_taken: List[str] = field(default_factory=list)
    resolved: bool = False
    carrier_response: Optional[Dict] = None
    compensation: Optional[Dict] = None
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return {
            'record_id': self.record_id,
            'order_id': self.order_id,
            'expected_date': self.expected_date,
            'current_date': self.current_date,
            'delay_days': self.delay_days,
            'stage': self.stage.value,
            'actions_taken': self.actions_taken,
            'resolved': self.resolved,
            'carrier_response': self.carrier_response,
            'compensation': self.compensation,
            'detected_at': self.detected_at,
        }


class DeliveryDelayHandler:
    """배송 지연 감지 및 자동 대응."""

    def __init__(self) -> None:
        self._records: Dict[str, DelayRecord] = {}

    def detect_delay(
        self,
        order_id: str,
        expected_date: str,
        current_date: str,
        delay_days: float,
    ) -> DelayRecord:
        stage = self._classify_stage(delay_days)
        record_id = f'delay_{uuid.uuid4().hex[:10]}'
        record = DelayRecord(
            record_id=record_id,
            order_id=order_id,
            expected_date=expected_date,
            current_date=current_date,
            delay_days=delay_days,
            stage=stage,
        )
        self._records[record_id] = record
        logger.info("배송 지연 감지: %s (order=%s, %.1f일)", record_id, order_id, delay_days)

        # 단계별 자동 대응
        self._auto_respond(record)
        return record

    def _classify_stage(self, delay_days: float) -> DelayStage:
        if delay_days <= 2:
            return DelayStage.minor
        if delay_days <= 5:
            return DelayStage.moderate
        return DelayStage.severe

    def _auto_respond(self, record: DelayRecord) -> None:
        if record.stage == DelayStage.minor:
            self._notify_customer(record)
        elif record.stage == DelayStage.moderate:
            self._notify_customer(record)
            self._query_carrier(record)
            self._offer_compensation(record)
        else:  # severe
            self._notify_customer(record)
            self._query_carrier(record)
            self._offer_compensation(record)
            self._reship_or_refund(record)

    def _notify_customer(self, record: DelayRecord) -> None:
        record.actions_taken.append(DelayAction.notify_customer.value)
        logger.info("고객 알림 (mock): %s", record.order_id)

    def _query_carrier(self, record: DelayRecord) -> None:
        record.actions_taken.append(DelayAction.query_carrier.value)
        # mock 택배사 응답
        record.carrier_response = {
            'queried_at': datetime.now(timezone.utc).isoformat(),
            'status': '조회 완료',
            'location': '물류센터',
            'estimated_delivery': '조회 중',
        }
        logger.info("택배사 조회 (mock): %s", record.order_id)

    def _offer_compensation(self, record: DelayRecord) -> None:
        record.actions_taken.append(DelayAction.offer_compensation.value)
        record.compensation = {
            'type': 'coupon',
            'amount': 3000,
            'reason': '배송 지연 보상',
        }
        logger.info("보상 제안 (mock): %s", record.order_id)

    def _reship_or_refund(self, record: DelayRecord) -> None:
        record.actions_taken.append(DelayAction.reship_or_refund.value)
        logger.warning("재발송/환불 옵션 제공 (mock): %s (%.1f일 지연)", record.order_id, record.delay_days)

    def resolve(self, record_id: str) -> DelayRecord:
        record = self._get_or_raise(record_id)
        record.resolved = True
        return record

    def get_record(self, record_id: str) -> Optional[DelayRecord]:
        return self._records.get(record_id)

    def list_records(self, order_id: Optional[str] = None, resolved: Optional[bool] = None) -> List[DelayRecord]:
        records = list(self._records.values())
        if order_id:
            records = [r for r in records if r.order_id == order_id]
        if resolved is not None:
            records = [r for r in records if r.resolved == resolved]
        return records

    def get_stats(self) -> Dict:
        records = list(self._records.values())
        by_stage: Dict[str, int] = {}
        for r in records:
            by_stage[r.stage.value] = by_stage.get(r.stage.value, 0) + 1
        resolved = sum(1 for r in records if r.resolved)
        return {
            'total': len(records),
            'resolved': resolved,
            'by_stage': by_stage,
            'avg_delay_days': sum(r.delay_days for r in records) / len(records) if records else 0.0,
        }

    def _get_or_raise(self, record_id: str) -> DelayRecord:
        record = self._records.get(record_id)
        if record is None:
            raise KeyError(f'지연 레코드를 찾을 수 없습니다: {record_id}')
        return record
