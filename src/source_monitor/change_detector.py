"""src/source_monitor/change_detector.py — 변동 감지기 (Phase 108).

ChangeDetector: 이전 상태 대비 변동 감지 + 심각도 자동 분류
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from .engine import SourceProduct
from .checkers import CheckResult, StockStatus

logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    listing_removed = 'listing_removed'
    price_increase = 'price_increase'
    price_decrease = 'price_decrease'
    out_of_stock = 'out_of_stock'
    back_in_stock = 'back_in_stock'
    seller_deactivated = 'seller_deactivated'
    shipping_changed = 'shipping_changed'
    description_changed = 'description_changed'
    rating_dropped = 'rating_dropped'


class Severity(str, Enum):
    critical = 'critical'
    high = 'high'
    medium = 'medium'
    low = 'low'


@dataclass
class ChangeEvent:
    event_id: str
    source_product_id: str
    change_type: ChangeType
    old_value: str
    new_value: str
    severity: Severity
    detected_at: str = ''
    auto_action_taken: Optional[str] = None

    def __post_init__(self):
        if not self.detected_at:
            self.detected_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'event_id': self.event_id,
            'source_product_id': self.source_product_id,
            'change_type': self.change_type.value if hasattr(self.change_type, 'value') else self.change_type,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'severity': self.severity.value if hasattr(self.severity, 'value') else self.severity,
            'detected_at': self.detected_at,
            'auto_action_taken': self.auto_action_taken,
        }


class ChangeDetector:
    """소싱처 상품 변동 감지기."""

    def __init__(self):
        self._events: List[ChangeEvent] = []

    def detect(self, product: SourceProduct, result: CheckResult) -> List[ChangeEvent]:
        """이전 상태 대비 변동 감지."""
        events: List[ChangeEvent] = []

        # 1) 리스팅 삭제
        if not result.is_alive and product.is_alive:
            events.append(self._make_event(
                product.source_product_id,
                ChangeType.listing_removed,
                old_value='alive',
                new_value='removed',
                severity=Severity.critical,
            ))

        # 2) 판매자 비활성화
        if not result.seller_active:
            events.append(self._make_event(
                product.source_product_id,
                ChangeType.seller_deactivated,
                old_value='active',
                new_value='inactive',
                severity=Severity.critical,
            ))

        # 3) 가격 변동
        if result.is_alive and product.current_price > 0:
            price_change_pct = (result.price - product.current_price) / product.current_price * 100
            if price_change_pct > 20:
                severity = Severity.high
                ct = ChangeType.price_increase
            elif price_change_pct > 10:
                severity = Severity.medium
                ct = ChangeType.price_increase
            elif price_change_pct > 0:
                severity = Severity.low
                ct = ChangeType.price_increase
            elif price_change_pct < -20:
                severity = Severity.medium
                ct = ChangeType.price_decrease
            elif price_change_pct < 0:
                severity = Severity.low
                ct = ChangeType.price_decrease
            else:
                price_change_pct = 0.0
                ct = None
                severity = Severity.low

            if ct and abs(price_change_pct) > 0.5:
                events.append(self._make_event(
                    product.source_product_id,
                    ct,
                    old_value=str(product.current_price),
                    new_value=str(result.price),
                    severity=severity,
                ))

        # 4) 재고 변동
        if result.is_alive:
            prev_out = product.stock_status == StockStatus.out_of_stock
            curr_out = result.stock_status == StockStatus.out_of_stock
            if not prev_out and curr_out:
                events.append(self._make_event(
                    product.source_product_id,
                    ChangeType.out_of_stock,
                    old_value=product.stock_status.value,
                    new_value=result.stock_status.value,
                    severity=Severity.high,
                ))
            elif prev_out and not curr_out:
                events.append(self._make_event(
                    product.source_product_id,
                    ChangeType.back_in_stock,
                    old_value=product.stock_status.value,
                    new_value=result.stock_status.value,
                    severity=Severity.low,
                ))
            elif product.stock_status != StockStatus.low_stock and result.stock_status == StockStatus.low_stock:
                events.append(self._make_event(
                    product.source_product_id,
                    ChangeType.out_of_stock,
                    old_value=product.stock_status.value,
                    new_value=result.stock_status.value,
                    severity=Severity.medium,
                ))

        self._events.extend(events)
        return events

    def _make_event(
        self,
        source_product_id: str,
        change_type: ChangeType,
        old_value: str,
        new_value: str,
        severity: Severity,
    ) -> ChangeEvent:
        return ChangeEvent(
            event_id=str(uuid.uuid4()),
            source_product_id=source_product_id,
            change_type=change_type,
            old_value=old_value,
            new_value=new_value,
            severity=severity,
        )

    def get_events(
        self,
        source_product_id: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[ChangeEvent]:
        events = self._events
        if source_product_id:
            events = [e for e in events if e.source_product_id == source_product_id]
        if severity:
            events = [e for e in events if e.severity.value == severity or e.severity == severity]
        return events

    def get_critical_events(self) -> List[ChangeEvent]:
        return self.get_events(severity='critical')

    def get_stats(self) -> dict:
        total = len(self._events)
        by_type: dict = {}
        by_severity: dict = {}
        for e in self._events:
            ct = e.change_type.value if hasattr(e.change_type, 'value') else str(e.change_type)
            sv = e.severity.value if hasattr(e.severity, 'value') else str(e.severity)
            by_type[ct] = by_type.get(ct, 0) + 1
            by_severity[sv] = by_severity.get(sv, 0) + 1
        return {'total': total, 'by_type': by_type, 'by_severity': by_severity}
