"""배송 예외 처리 — CS 티켓 자동 생성 및 운영자 알림."""
from __future__ import annotations

import logging
from typing import Optional

from .models import DeliveryAnomaly

logger = logging.getLogger(__name__)


class DeliveryExceptionHandler:
    """배송 예외 처리기 — CS 티켓 자동 생성."""

    def __init__(self, ticket_manager=None, notification_hub=None) -> None:
        # 의존성 주입 (None이면 지연 초기화)
        self._ticket_manager = ticket_manager
        self._hub = notification_hub

    def handle_exception(
        self,
        tracking_no: str,
        order_id: str,
        user_id: str,
        reason: str = '배송 예외 발생',
    ) -> Optional[object]:
        """exception 상태 발생 시 CS 티켓 생성."""
        try:
            manager = self._get_ticket_manager()
            ticket = manager.create(
                customer_id=user_id,
                subject=f'[배송 예외] 운송장 {tracking_no}',
                description=f'주문 {order_id} 배송 예외 발생.\n사유: {reason}',
                priority='high',
            )
            logger.info("배송 예외 CS 티켓 생성: %s → ticket %s", tracking_no, ticket.id)
            self._notify_operator(tracking_no, order_id, reason, ticket.id)
            return ticket
        except Exception as exc:
            logger.error("배송 예외 티켓 생성 실패: %s — %s", tracking_no, exc)
            return None

    def handle_anomaly(self, anomaly: DeliveryAnomaly, user_id: str = '') -> Optional[object]:
        """이상 감지 시 심각도에 따라 CS 티켓 생성."""
        # high 심각도만 자동 티켓 생성
        if anomaly.severity != 'high':
            logger.info("anomaly 심각도 %s — 티켓 생성 생략: %s", anomaly.severity, anomaly.tracking_no)
            return None
        reason = f'배송 이상 감지: {anomaly.anomaly_type} (심각도: {anomaly.severity})'
        return self.handle_exception(
            tracking_no=anomaly.tracking_no,
            order_id=anomaly.order_id,
            user_id=user_id or anomaly.order_id,
            reason=reason,
        )

    def _notify_operator(self, tracking_no: str, order_id: str, reason: str, ticket_id: str) -> None:
        """운영자에게 즉시 텔레그램 알림 발송."""
        try:
            hub = self._get_hub()
            msg = (
                f"🚨 [배송 예외] 운송장: {tracking_no}\n"
                f"주문: {order_id}\n사유: {reason}\n티켓 ID: {ticket_id}"
            )
            hub.dispatch('system_alert', 'operator', msg)
        except Exception as exc:
            logger.warning("운영자 알림 실패: %s", exc)

    def _get_ticket_manager(self):
        if self._ticket_manager is None:
            from ..customer_service.ticket_manager import TicketManager
            self._ticket_manager = TicketManager()
        return self._ticket_manager

    def _get_hub(self):
        if self._hub is None:
            from ..notifications.notification_hub import NotificationHub
            self._hub = NotificationHub()
        return self._hub
