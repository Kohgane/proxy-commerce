"""src/event_sourcing/order_aggregate.py — 주문 애그리거트 예제."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .aggregate import Aggregate
from .event import Event


class OrderAggregate(Aggregate):
    """주문 애그리거트 — 이벤트 소싱 예제.

    지원 이벤트: OrderCreated, OrderConfirmed, OrderShipped, OrderCompleted, OrderCancelled
    """

    def __init__(self, aggregate_id: str) -> None:
        super().__init__(aggregate_id)
        self._uncommitted: List[Event] = []

    def create_order(self, customer_id: str, items: list, total_amount: float) -> Event:
        """주문 생성 이벤트 발행."""
        event = Event(
            event_type="OrderCreated",
            aggregate_id=self.aggregate_id,
            data={
                "customer_id": customer_id,
                "items": items,
                "total_amount": total_amount,
                "status": "created",
            },
            version=self._version + 1,
        )
        self.apply(event)
        self._uncommitted.append(event)
        return event

    def confirm_order(self, payment_ref: str = "") -> Event:
        """주문 확인 이벤트 발행."""
        event = Event(
            event_type="OrderConfirmed",
            aggregate_id=self.aggregate_id,
            data={"status": "confirmed", "payment_ref": payment_ref},
            version=self._version + 1,
        )
        self.apply(event)
        self._uncommitted.append(event)
        return event

    def ship_order(self, tracking_number: str = "") -> Event:
        """배송 시작 이벤트 발행."""
        event = Event(
            event_type="OrderShipped",
            aggregate_id=self.aggregate_id,
            data={"status": "shipped", "tracking_number": tracking_number},
            version=self._version + 1,
        )
        self.apply(event)
        self._uncommitted.append(event)
        return event

    def complete_order(self) -> Event:
        """주문 완료 이벤트 발행."""
        event = Event(
            event_type="OrderCompleted",
            aggregate_id=self.aggregate_id,
            data={"status": "completed"},
            version=self._version + 1,
        )
        self.apply(event)
        self._uncommitted.append(event)
        return event

    def cancel_order(self, reason: str = "") -> Event:
        """주문 취소 이벤트 발행."""
        event = Event(
            event_type="OrderCancelled",
            aggregate_id=self.aggregate_id,
            data={"status": "cancelled", "reason": reason},
            version=self._version + 1,
        )
        self.apply(event)
        self._uncommitted.append(event)
        return event

    def get_uncommitted_events(self) -> List[Event]:
        return list(self._uncommitted)

    def mark_events_as_committed(self) -> None:
        self._uncommitted.clear()

    def get_status(self) -> Optional[str]:
        return self._state.get("status")
