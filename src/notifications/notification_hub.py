"""src/notifications/notification_hub.py — Phase 35: 알림 허브 (이벤트 기반)."""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

EVENT_ORDER_PLACED = 'order_placed'
EVENT_ORDER_SHIPPED = 'order_shipped'
EVENT_STOCK_LOW = 'stock_low'
EVENT_PRICE_CHANGED = 'price_changed'
EVENT_CS_TICKET = 'cs_ticket'
EVENT_SYSTEM_ALERT = 'system_alert'

ALL_EVENTS = {
    EVENT_ORDER_PLACED, EVENT_ORDER_SHIPPED, EVENT_STOCK_LOW,
    EVENT_PRICE_CHANGED, EVENT_CS_TICKET, EVENT_SYSTEM_ALERT,
}


class NotificationChannel(ABC):
    """알림 채널 추상 기반 클래스."""

    @abstractmethod
    def send(self, recipient: str, message: str, template_data: dict = None) -> bool:
        """알림 발송."""


class NotificationHub:
    """이벤트 기반 알림 허브 — 다중 채널 동시 발송."""

    _EVENT_CHANNEL_MAP = {
        EVENT_ORDER_PLACED: ['email', 'telegram'],
        EVENT_ORDER_SHIPPED: ['email', 'telegram'],
        EVENT_STOCK_LOW: ['slack', 'telegram'],
        EVENT_PRICE_CHANGED: ['slack'],
        EVENT_CS_TICKET: ['email', 'slack'],
        EVENT_SYSTEM_ALERT: ['slack', 'telegram'],
    }

    def __init__(self):
        self._channels: dict = {}
        self._dispatched: list = []

    def register_channel(self, name: str, channel: NotificationChannel) -> None:
        """채널 등록."""
        self._channels[name] = channel
        logger.info("알림 채널 등록: %s", name)

    def dispatch(self, event_type: str, recipient: str, message: str, template_data: dict = None) -> dict:
        """이벤트 타입에 맞는 채널로 알림 발송.

        Args:
            event_type: 이벤트 유형
            recipient: 수신자
            message: 메시지
            template_data: 템플릿 데이터

        Returns:
            채널별 발송 결과 딕셔너리
        """
        channel_names = self._EVENT_CHANNEL_MAP.get(event_type, [])
        results = {}

        for ch_name in channel_names:
            channel = self._channels.get(ch_name)
            if channel is None:
                results[ch_name] = False
                logger.warning("채널 미등록: %s", ch_name)
                continue
            try:
                ok = channel.send(recipient, message, template_data)
                results[ch_name] = ok
            except Exception as exc:
                logger.error("채널 %s 발송 오류: %s", ch_name, exc)
                results[ch_name] = False

        record = {
            'event_type': event_type,
            'recipient': recipient,
            'channels': results,
        }
        self._dispatched.append(record)
        return results

    def get_dispatched(self) -> list:
        """발송 이력 반환."""
        return list(self._dispatched)
