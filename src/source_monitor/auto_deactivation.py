"""src/source_monitor/auto_deactivation.py — 자동 비활성화 서비스 (Phase 108).

AutoDeactivationService: 문제 감지 시 내 판매 채널 자동 비활성화 + 재활성화
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from .change_detector import ChangeEvent, ChangeType, Severity

logger = logging.getLogger(__name__)


class DeactivationAction(str, Enum):
    immediate_deactivate = 'immediate_deactivate'
    temp_deactivate = 'temp_deactivate'
    notify_only = 'notify_only'
    search_alternative = 'search_alternative'
    admin_review = 'admin_review'


@dataclass
class DeactivationRule:
    rule_id: str
    trigger_type: str
    action: DeactivationAction
    delay_minutes: int = 0
    notify: bool = True
    description: str = ''

    def to_dict(self) -> dict:
        return {
            'rule_id': self.rule_id,
            'trigger_type': self.trigger_type,
            'action': self.action.value if hasattr(self.action, 'value') else self.action,
            'delay_minutes': self.delay_minutes,
            'notify': self.notify,
            'description': self.description,
        }


@dataclass
class DeactivationRecord:
    record_id: str
    source_product_id: str
    my_product_id: str
    reason: str
    action_taken: DeactivationAction
    deactivated_at: str = ''
    reactivated_at: Optional[str] = None
    is_active: bool = False

    def __post_init__(self):
        if not self.deactivated_at:
            self.deactivated_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'record_id': self.record_id,
            'source_product_id': self.source_product_id,
            'my_product_id': self.my_product_id,
            'reason': self.reason,
            'action_taken': self.action_taken.value if hasattr(self.action_taken, 'value') else self.action_taken,
            'deactivated_at': self.deactivated_at,
            'reactivated_at': self.reactivated_at,
            'is_active': self.is_active,
        }


# 기본 규칙
_DEFAULT_RULES: List[DeactivationRule] = [
    DeactivationRule(
        rule_id='rule_listing_removed',
        trigger_type=ChangeType.listing_removed.value,
        action=DeactivationAction.immediate_deactivate,
        delay_minutes=0,
        notify=True,
        description='상품 삭제 → 즉시 내 상품 비활성화',
    ),
    DeactivationRule(
        rule_id='rule_out_of_stock',
        trigger_type=ChangeType.out_of_stock.value,
        action=DeactivationAction.immediate_deactivate,
        delay_minutes=0,
        notify=True,
        description='품절 → 즉시 비활성화 + 대체 소싱처 검색',
    ),
    DeactivationRule(
        rule_id='rule_seller_deactivated',
        trigger_type=ChangeType.seller_deactivated.value,
        action=DeactivationAction.immediate_deactivate,
        delay_minutes=0,
        notify=True,
        description='판매자 비활성화 → 즉시 비활성화',
    ),
    DeactivationRule(
        rule_id='rule_price_increase_high',
        trigger_type='price_increase_high',
        action=DeactivationAction.temp_deactivate,
        delay_minutes=0,
        notify=True,
        description='가격 20%+ 인상 → 일시 비활성화 + 관리자 확인 요청',
    ),
    DeactivationRule(
        rule_id='rule_price_increase_medium',
        trigger_type='price_increase_medium',
        action=DeactivationAction.notify_only,
        delay_minutes=0,
        notify=True,
        description='가격 10~20% 인상 → 알림만 (자동 판매가 조정 제안)',
    ),
]


class AutoDeactivationService:
    """자동 비활성화 서비스."""

    def __init__(self):
        self._rules: List[DeactivationRule] = list(_DEFAULT_RULES)
        self._records: Dict[str, DeactivationRecord] = {}

    def process_event(self, event: ChangeEvent, product) -> Optional[str]:
        """변동 이벤트에 따른 자동 대응 처리."""
        rule = self._find_rule(event)
        if not rule:
            return None

        action_str = rule.action.value if hasattr(rule.action, 'value') else str(rule.action)

        # 기록
        rec_id = str(uuid.uuid4())
        record = DeactivationRecord(
            record_id=rec_id,
            source_product_id=event.source_product_id,
            my_product_id=getattr(product, 'my_product_id', ''),
            reason=f"{event.change_type.value}: {event.old_value} → {event.new_value}",
            action_taken=rule.action,
            is_active=rule.action in (
                DeactivationAction.immediate_deactivate,
                DeactivationAction.temp_deactivate,
            ),
        )
        self._records[rec_id] = record

        logger.info(
            "자동 대응: %s → %s (상품: %s)",
            event.change_type.value,
            action_str,
            event.source_product_id,
        )
        return action_str

    def _find_rule(self, event: ChangeEvent) -> Optional[DeactivationRule]:
        ct = event.change_type.value if hasattr(event.change_type, 'value') else str(event.change_type)
        sv = event.severity.value if hasattr(event.severity, 'value') else str(event.severity)

        # 심각도 기반 가격 인상 구분
        if ct == ChangeType.price_increase.value:
            if sv == Severity.high.value:
                ct = 'price_increase_high'
            elif sv == Severity.medium.value:
                ct = 'price_increase_medium'

        for rule in self._rules:
            if rule.trigger_type == ct:
                return rule
        return None

    def add_rule(self, data: dict) -> DeactivationRule:
        rule = DeactivationRule(
            rule_id=data.get('rule_id') or str(uuid.uuid4()),
            trigger_type=data.get('trigger_type', ''),
            action=DeactivationAction(data.get('action', 'notify_only')),
            delay_minutes=int(data.get('delay_minutes', 0)),
            notify=bool(data.get('notify', True)),
            description=data.get('description', ''),
        )
        self._rules.append(rule)
        return rule

    def list_rules(self) -> List[DeactivationRule]:
        return list(self._rules)

    def list_deactivated(self) -> List[DeactivationRecord]:
        return [r for r in self._records.values() if r.is_active]

    def reactivate(self, record_id: str) -> bool:
        record = self._records.get(record_id)
        if record and record.is_active:
            record.is_active = False
            record.reactivated_at = datetime.now(tz=timezone.utc).isoformat()
            return True
        return False

    def get_history(self, source_product_id: Optional[str] = None) -> List[DeactivationRecord]:
        records = list(self._records.values())
        if source_product_id:
            records = [r for r in records if r.source_product_id == source_product_id]
        return records
