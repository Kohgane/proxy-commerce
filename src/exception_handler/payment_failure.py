"""src/exception_handler/payment_failure.py — 결제 실패 대응 (Phase 105)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PaymentFailureReason(str, Enum):
    insufficient_balance = 'insufficient_balance'
    card_expired = 'card_expired'
    limit_exceeded = 'limit_exceeded'
    system_error = 'system_error'
    invalid_card = 'invalid_card'
    declined = 'declined'


class PaymentFailureStatus(str, Enum):
    detected = 'detected'
    retrying = 'retrying'
    alternative_attempted = 'alternative_attempted'
    resolved = 'resolved'
    failed = 'failed'


@dataclass
class PaymentFailureRecord:
    record_id: str
    order_id: str
    amount: float
    reason: PaymentFailureReason
    status: PaymentFailureStatus = PaymentFailureStatus.detected
    original_method: str = 'card'
    alternative_method: Optional[str] = None
    retry_count: int = 0
    resolved: bool = False
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'record_id': self.record_id,
            'order_id': self.order_id,
            'amount': self.amount,
            'reason': self.reason.value,
            'status': self.status.value,
            'original_method': self.original_method,
            'alternative_method': self.alternative_method,
            'retry_count': self.retry_count,
            'resolved': self.resolved,
            'detected_at': self.detected_at,
            'resolved_at': self.resolved_at,
            'actions': self.actions,
        }


class PaymentFailureHandler:
    """결제 실패 감지 및 자동 복구."""

    # 실패 유형별 자동 대응 전략
    _STRATEGY: Dict[PaymentFailureReason, str] = {
        PaymentFailureReason.insufficient_balance: '대안 결제수단 자동 전환',
        PaymentFailureReason.card_expired: '등록 카드 목록 확인 및 유효 카드로 전환',
        PaymentFailureReason.limit_exceeded: '분할 결제 또는 대안 수단 전환',
        PaymentFailureReason.system_error: '재시도 스케줄링',
        PaymentFailureReason.invalid_card: '결제 수단 재등록 요청',
        PaymentFailureReason.declined: '다른 카드/간편결제 전환',
    }

    # 대안 결제 수단 우선순위
    _ALTERNATIVES = ['kakao_pay', 'naver_pay', 'toss', 'bank_transfer', 'virtual_account']

    def __init__(self) -> None:
        self._records: Dict[str, PaymentFailureRecord] = {}

    def detect(
        self,
        order_id: str,
        amount: float,
        reason: PaymentFailureReason,
        original_method: str = 'card',
    ) -> PaymentFailureRecord:
        record_id = f'pf_{uuid.uuid4().hex[:10]}'
        record = PaymentFailureRecord(
            record_id=record_id,
            order_id=order_id,
            amount=amount,
            reason=reason,
            original_method=original_method,
        )
        self._records[record_id] = record
        logger.info("결제 실패 감지: %s (order=%s, reason=%s)", record_id, order_id, reason.value)

        # 자동 대응
        self._auto_respond(record)
        return record

    def _auto_respond(self, record: PaymentFailureRecord) -> None:
        strategy = self._STRATEGY.get(record.reason, '수동 확인 필요')
        record.actions.append(strategy)

        if record.reason == PaymentFailureReason.system_error:
            self._schedule_retry(record)
        else:
            self._switch_alternative(record)

    def _switch_alternative(self, record: PaymentFailureRecord) -> None:
        alt = self._ALTERNATIVES[0]
        record.alternative_method = alt
        record.status = PaymentFailureStatus.alternative_attempted
        record.actions.append(f'대안 결제수단 전환: {alt}')
        logger.info("대안 결제 전환 (mock): %s → %s", record.order_id, alt)

    def _schedule_retry(self, record: PaymentFailureRecord) -> None:
        record.status = PaymentFailureStatus.retrying
        record.retry_count += 1
        record.actions.append(f'재시도 스케줄링 (#{record.retry_count})')
        logger.info("결제 재시도 스케줄링 (mock): %s", record.order_id)

    def retry(self, record_id: str) -> PaymentFailureRecord:
        record = self._get_or_raise(record_id)
        record.retry_count += 1
        record.status = PaymentFailureStatus.retrying
        record.actions.append(f'수동 재시도 (#{record.retry_count})')
        # mock: 재시도 성공 처리
        self.resolve(record_id)
        return record

    def resolve(self, record_id: str) -> PaymentFailureRecord:
        record = self._get_or_raise(record_id)
        record.resolved = True
        record.status = PaymentFailureStatus.resolved
        record.resolved_at = datetime.now(timezone.utc).isoformat()
        logger.info("결제 실패 해결: %s", record_id)
        return record

    def get_record(self, record_id: str) -> Optional[PaymentFailureRecord]:
        return self._records.get(record_id)

    def list_records(
        self,
        order_id: Optional[str] = None,
        resolved: Optional[bool] = None,
    ) -> List[PaymentFailureRecord]:
        records = list(self._records.values())
        if order_id:
            records = [r for r in records if r.order_id == order_id]
        if resolved is not None:
            records = [r for r in records if r.resolved == resolved]
        return records

    def get_stats(self) -> Dict:
        records = list(self._records.values())
        by_reason: Dict[str, int] = {}
        for r in records:
            by_reason[r.reason.value] = by_reason.get(r.reason.value, 0) + 1
        resolved = sum(1 for r in records if r.resolved)
        total = len(records)
        return {
            'total': total,
            'resolved': resolved,
            'resolution_rate': resolved / total if total else 0.0,
            'by_reason': by_reason,
            'total_amount_affected': sum(r.amount for r in records),
        }

    def _get_or_raise(self, record_id: str) -> PaymentFailureRecord:
        record = self._records.get(record_id)
        if record is None:
            raise KeyError(f'결제 실패 레코드를 찾을 수 없습니다: {record_id}')
        return record
