"""주문 알림 매니저 모듈.

AlertManager는 주문 상태를 분석해 적절한 텔레그램 알림을 발송합니다.
"""

import logging

from .alert_dispatcher import AlertDispatcher
from .telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)

# 플랫폼 상태 코드 → 내부 상태 매핑
_STATUS_MAP = {
    # 주문 접수
    'ACCEPT': 'order_received',
    'PAY_WAITING': 'order_received',
    # 결제 확인
    'PAYED': 'payment_confirmed',
    'INSTRUCT': 'payment_confirmed',
    'PURCHASE_DECIDED': 'payment_confirmed',
    # 배송
    'DEPARTURE': 'shipping',
    'DELIVERING': 'shipping',
    # 배송 완료
    'DELIVERED': 'delivered',
    # 취소
    'CANCEL_REQUEST': 'cancelled',
    'CANCELED': 'cancelled',
    # 환불
    'RETURN_REQUEST': 'refunded',
    'RETURNED': 'refunded',
}

_SUPPORTED_STATUSES = frozenset({
    'order_received',
    'payment_confirmed',
    'shipping',
    'delivered',
    'cancelled',
    'refunded',
})


class AlertManager:
    """주문 알림 발송 매니저.

    주문 딕셔너리를 받아 상태에 따라 텔레그램 알림을 발송합니다.
    AlertDispatcher(기존 알림)와 TelegramNotifier(Inline Keyboard 지원)를 내부적으로 사용합니다.
    """

    def __init__(
        self,
        dispatcher: AlertDispatcher = None,
        notifier: TelegramNotifier = None,
    ):
        """초기화.

        Args:
            dispatcher: AlertDispatcher 인스턴스 (None이면 기본값 생성)
            notifier: TelegramNotifier 인스턴스 (None이면 기본값 생성)
        """
        self._dispatcher = dispatcher or AlertDispatcher()
        self._notifier = notifier or TelegramNotifier()

    # ── public API ───────────────────────────────────────────

    def dispatch(self, order: dict) -> bool:
        """주문 딕셔너리에서 상태를 읽어 알림 발송.

        플랫폼 상태 코드(ACCEPT, PAYED 등)와 내부 상태 코드(order_received 등)를
        모두 지원합니다.

        Args:
            order: 정규화된 주문 딕셔너리

        Returns:
            발송 성공 여부
        """
        raw_status = order.get('status', '')
        internal_status = _STATUS_MAP.get(raw_status, raw_status)

        if internal_status not in _SUPPORTED_STATUSES:
            logger.warning("지원하지 않는 주문 상태: %s — 기본 알림 발송", raw_status)
            return self._dispatcher.send_new_order_alert(order)

        return self._notifier.send_order_alert(order, internal_status)

    def dispatch_status_change(self, order: dict, new_status: str) -> bool:
        """주문 상태 변경 알림 발송.

        Args:
            order: 정규화된 주문 딕셔너리
            new_status: 새로운 상태 코드 (플랫폼 코드 또는 내부 코드)

        Returns:
            발송 성공 여부
        """
        internal_status = _STATUS_MAP.get(new_status, new_status)

        if internal_status in _SUPPORTED_STATUSES:
            return self._notifier.send_order_alert(order, internal_status)

        # 내부 상태로 매핑되지 않는 경우 기존 dispatcher 사용
        return self._dispatcher.send_status_change_alert(order, new_status)
