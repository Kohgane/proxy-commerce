"""src/exception_handler/engine.py — ExceptionEngine 오케스트레이터 (Phase 105)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ExceptionType(str, Enum):
    price_change = 'price_change'
    out_of_stock = 'out_of_stock'
    damaged_product = 'damaged_product'
    delivery_delay = 'delivery_delay'
    payment_failure = 'payment_failure'
    customs_hold = 'customs_hold'
    seller_issue = 'seller_issue'
    wrong_item = 'wrong_item'
    quantity_mismatch = 'quantity_mismatch'


class ExceptionSeverity(str, Enum):
    low = 'low'
    medium = 'medium'
    high = 'high'
    critical = 'critical'


class ExceptionStatus(str, Enum):
    detected = 'detected'
    analyzing = 'analyzing'
    action_taken = 'action_taken'
    waiting_response = 'waiting_response'
    resolved = 'resolved'
    escalated = 'escalated'
    manual_required = 'manual_required'


@dataclass
class ExceptionCase:
    case_id: str
    type: ExceptionType
    severity: ExceptionSeverity
    status: ExceptionStatus = ExceptionStatus.detected
    order_id: Optional[str] = None
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolution: Optional[str] = None
    retry_count: int = 0
    metadata: Dict = field(default_factory=dict)
    notes: str = ''

    def update_status(self, new_status: ExceptionStatus) -> None:
        self.status = new_status
        if new_status in (ExceptionStatus.resolved, ExceptionStatus.escalated):
            self.resolved_at = datetime.now(timezone.utc).isoformat()
        logger.debug("ExceptionCase %s → %s", self.case_id, new_status.value)

    def to_dict(self) -> Dict:
        return {
            'case_id': self.case_id,
            'type': self.type.value,
            'severity': self.severity.value,
            'status': self.status.value,
            'order_id': self.order_id,
            'detected_at': self.detected_at,
            'resolved_at': self.resolved_at,
            'resolution': self.resolution,
            'retry_count': self.retry_count,
            'metadata': self.metadata,
            'notes': self.notes,
        }


class ExceptionEngine:
    """예외 감지 → 분류 → 대응 전략 결정 → 자동 복구 → 알림 → 이력 관리."""

    # severity 기본 매핑
    _DEFAULT_SEVERITY: Dict[ExceptionType, ExceptionSeverity] = {
        ExceptionType.price_change: ExceptionSeverity.medium,
        ExceptionType.out_of_stock: ExceptionSeverity.high,
        ExceptionType.damaged_product: ExceptionSeverity.high,
        ExceptionType.delivery_delay: ExceptionSeverity.medium,
        ExceptionType.payment_failure: ExceptionSeverity.high,
        ExceptionType.customs_hold: ExceptionSeverity.medium,
        ExceptionType.seller_issue: ExceptionSeverity.high,
        ExceptionType.wrong_item: ExceptionSeverity.high,
        ExceptionType.quantity_mismatch: ExceptionSeverity.medium,
    }

    def __init__(self) -> None:
        self._cases: Dict[str, ExceptionCase] = {}

    # ── 생성 ──────────────────────────────────────────────────────────────────

    def detect(
        self,
        exception_type: ExceptionType,
        order_id: Optional[str] = None,
        severity: Optional[ExceptionSeverity] = None,
        metadata: Optional[Dict] = None,
        notes: str = '',
    ) -> ExceptionCase:
        case_id = f'exc_{uuid.uuid4().hex[:10]}'
        eff_severity = severity or self._DEFAULT_SEVERITY.get(exception_type, ExceptionSeverity.medium)
        case = ExceptionCase(
            case_id=case_id,
            type=exception_type,
            severity=eff_severity,
            order_id=order_id,
            metadata=metadata or {},
            notes=notes,
        )
        self._cases[case_id] = case
        logger.info("예외 감지: %s (type=%s, severity=%s)", case_id, exception_type.value, eff_severity.value)
        return case

    # ── 조회 ──────────────────────────────────────────────────────────────────

    def get_case(self, case_id: str) -> Optional[ExceptionCase]:
        return self._cases.get(case_id)

    def list_cases(
        self,
        status: Optional[ExceptionStatus] = None,
        exception_type: Optional[ExceptionType] = None,
        severity: Optional[ExceptionSeverity] = None,
    ) -> List[ExceptionCase]:
        cases = list(self._cases.values())
        if status:
            cases = [c for c in cases if c.status == status]
        if exception_type:
            cases = [c for c in cases if c.type == exception_type]
        if severity:
            cases = [c for c in cases if c.severity == severity]
        return cases

    # ── 상태 변경 ─────────────────────────────────────────────────────────────

    def analyze(self, case_id: str) -> ExceptionCase:
        case = self._get_or_raise(case_id)
        case.update_status(ExceptionStatus.analyzing)
        return case

    def take_action(self, case_id: str, action: str = '') -> ExceptionCase:
        case = self._get_or_raise(case_id)
        case.update_status(ExceptionStatus.action_taken)
        if action:
            case.notes = action
        return case

    def wait_response(self, case_id: str) -> ExceptionCase:
        case = self._get_or_raise(case_id)
        case.update_status(ExceptionStatus.waiting_response)
        return case

    def resolve(self, case_id: str, resolution: str = '') -> ExceptionCase:
        case = self._get_or_raise(case_id)
        case.resolution = resolution
        case.update_status(ExceptionStatus.resolved)
        logger.info("예외 해결: %s — %s", case_id, resolution)
        return case

    def escalate(self, case_id: str, reason: str = '') -> ExceptionCase:
        case = self._get_or_raise(case_id)
        case.notes = reason
        case.update_status(ExceptionStatus.escalated)
        logger.warning("예외 에스컬레이션: %s — %s", case_id, reason)
        return case

    def mark_manual_required(self, case_id: str) -> ExceptionCase:
        case = self._get_or_raise(case_id)
        case.update_status(ExceptionStatus.manual_required)
        return case

    def increment_retry(self, case_id: str) -> ExceptionCase:
        case = self._get_or_raise(case_id)
        case.retry_count += 1
        return case

    # ── 통계 ──────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        cases = list(self._cases.values())
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        resolved_count = 0

        for c in cases:
            by_type[c.type.value] = by_type.get(c.type.value, 0) + 1
            by_severity[c.severity.value] = by_severity.get(c.severity.value, 0) + 1
            by_status[c.status.value] = by_status.get(c.status.value, 0) + 1
            if c.status == ExceptionStatus.resolved:
                resolved_count += 1

        total = len(cases)
        return {
            'total': total,
            'resolved': resolved_count,
            'resolution_rate': resolved_count / total if total else 0.0,
            'by_type': by_type,
            'by_severity': by_severity,
            'by_status': by_status,
        }

    # ── 내부 ──────────────────────────────────────────────────────────────────

    def _get_or_raise(self, case_id: str) -> ExceptionCase:
        case = self._cases.get(case_id)
        if case is None:
            raise KeyError(f'예외 케이스를 찾을 수 없습니다: {case_id}')
        return case
