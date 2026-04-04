"""src/mobile_api/mobile_notification.py — 모바일 푸시 알림 서비스."""
from __future__ import annotations

import time
import uuid
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PushNotification:
    notification_id: str
    user_id: str
    title: str
    body: str
    notification_type: str  # order_status/price_drop/restock/delivery/promotion
    data: dict = field(default_factory=dict)
    sent_at: float = field(default_factory=time.time)
    is_read: bool = False


@dataclass
class NotificationHistory:
    user_id: str
    notifications: list[PushNotification] = field(default_factory=list)


class PushProvider(ABC):
    """푸시 공급자 ABC."""

    @abstractmethod
    def send(self, device_token: str, title: str, body: str, data: dict) -> bool:
        ...


class FCMProvider(PushProvider):
    """Firebase Cloud Messaging (Android) mock 구현."""

    def send(self, device_token: str, title: str, body: str, data: dict) -> bool:
        logger.debug("FCM send to %s: %s", device_token[:8] if device_token else '', title)
        return bool(device_token)


class APNsProvider(PushProvider):
    """Apple Push Notification service (iOS) mock 구현."""

    def send(self, device_token: str, title: str, body: str, data: dict) -> bool:
        logger.debug("APNs send to %s: %s", device_token[:8] if device_token else '', title)
        return bool(device_token)


class MobilePushService:
    """모바일 푸시 알림 서비스."""

    def __init__(self):
        self._tokens: dict[str, dict] = {}  # user_id -> {device_id: {platform, token}}
        self._notifications: dict[str, list[PushNotification]] = {}
        self._fcm = FCMProvider()
        self._apns = APNsProvider()

    def register_push_token(self, user_id: str, device_id: str, platform: str, token: str) -> bool:
        user_tokens = self._tokens.setdefault(user_id, {})
        user_tokens[device_id] = {'platform': platform, 'token': token}
        return True

    def revoke_push_token(self, user_id: str, device_id: str) -> bool:
        user_tokens = self._tokens.get(user_id, {})
        if device_id in user_tokens:
            del user_tokens[device_id]
            return True
        return False

    def send_notification(self, user_id: str, title: str, body: str,
                          notification_type: str, data: Optional[dict] = None) -> PushNotification:
        notif = PushNotification(
            notification_id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            body=body,
            notification_type=notification_type,
            data=data or {},
        )
        # Send via providers
        user_tokens = self._tokens.get(user_id, {})
        for device_id, token_info in user_tokens.items():
            platform = token_info.get('platform', '')
            token = token_info.get('token', '')
            try:
                if platform == 'android':
                    self._fcm.send(token, title, body, notif.data)
                elif platform == 'ios':
                    self._apns.send(token, title, body, notif.data)
                else:
                    self._fcm.send(token, title, body, notif.data)
            except Exception as exc:
                logger.warning("Push send error for %s: %s", device_id, exc)

        self._notifications.setdefault(user_id, []).append(notif)
        return notif

    def send_order_status_notification(self, user_id: str, order_id: str, status: str) -> PushNotification:
        return self.send_notification(
            user_id, '주문 상태 업데이트',
            f'주문 {order_id[:8]}의 상태가 {status}로 변경되었습니다.',
            'order_status', {'order_id': order_id, 'status': status}
        )

    def send_price_drop_notification(self, user_id: str, sku: str, old_price: float, new_price: float) -> PushNotification:
        return self.send_notification(
            user_id, '가격 인하 알림',
            f'{sku} 상품 가격이 {old_price:.0f}원에서 {new_price:.0f}원으로 인하되었습니다.',
            'price_drop', {'sku': sku, 'old_price': old_price, 'new_price': new_price}
        )

    def send_restock_notification(self, user_id: str, sku: str) -> PushNotification:
        return self.send_notification(
            user_id, '재입고 알림',
            f'{sku} 상품이 재입고되었습니다.',
            'restock', {'sku': sku}
        )

    def send_delivery_notification(self, user_id: str, order_id: str) -> PushNotification:
        return self.send_notification(
            user_id, '배송 완료',
            f'주문 {order_id[:8]}이(가) 배송 완료되었습니다.',
            'delivery', {'order_id': order_id}
        )

    def send_promotion_notification(self, user_id: str, title: str, body: str) -> PushNotification:
        return self.send_notification(user_id, title, body, 'promotion')

    def get_notification_history(self, user_id: str, limit: int = 50, unread_only: bool = False) -> list[dict]:
        notifs = self._notifications.get(user_id, [])
        if unread_only:
            notifs = [n for n in notifs if not n.is_read]
        recent = notifs[-limit:]
        return [
            {
                'notification_id': n.notification_id,
                'user_id': n.user_id,
                'title': n.title,
                'body': n.body,
                'notification_type': n.notification_type,
                'data': n.data,
                'sent_at': n.sent_at,
                'is_read': n.is_read,
            }
            for n in reversed(recent)
        ]

    def mark_as_read(self, user_id: str, notification_id: str) -> bool:
        for n in self._notifications.get(user_id, []):
            if n.notification_id == notification_id:
                n.is_read = True
                return True
        return False
