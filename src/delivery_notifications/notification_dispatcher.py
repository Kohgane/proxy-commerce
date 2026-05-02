"""배송 알림 발송 오케스트레이션 — NotificationHub 위임."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from .models import DeliveryEvent, DeliveryNotification, NotificationPreference
from .templates import render_template

logger = logging.getLogger(__name__)

# 조용 시간에도 무조건 발송되는 중요 상태
ALWAYS_SEND_STATUSES = {'delivered', 'exception'}


class DeliveryNotificationDispatcher:
    """채널별 배송 알림 발송 오케스트레이터."""

    def __init__(self, hub=None, preference_manager=None) -> None:
        self._hub = hub
        self._pref_mgr = preference_manager
        # 발송 이력 인메모리 저장
        self._history: List[DeliveryNotification] = []

    def dispatch(
        self,
        event: DeliveryEvent,
        preference: NotificationPreference,
        order_id: str = '',
    ) -> List[DeliveryNotification]:
        """이벤트에 맞는 채널로 알림 발송."""
        results: List[DeliveryNotification] = []
        hub = self._get_hub()

        # 조용 시간 체크 (중요 이벤트는 제외)
        if event.status not in ALWAYS_SEND_STATUSES:
            if self._is_quiet_time(preference):
                logger.info("조용 시간 — 알림 생략: %s", event.tracking_no)
                return results

        message = render_template(
            status=event.status,
            language=preference.language,
            order_id=order_id or event.tracking_no,
            tracking_no=event.tracking_no,
            carrier='',
            location=event.location or '',
            eta='',
        )

        for channel in preference.channels:
            try:
                ok = self._send_to_channel(hub, channel, preference.user_id, message)
            except Exception as exc:
                logger.error("채널 %s 발송 오류: %s", channel, exc)
                ok = False

            notif = DeliveryNotification(
                order_id=order_id,
                tracking_no=event.tracking_no,
                carrier='',
                status_from='',
                status_to=event.status,
                channel=channel,
                success=ok,
            )
            self._history.append(notif)
            results.append(notif)

        return results

    def get_history(self, order_id: str = '') -> List[DeliveryNotification]:
        """발송 이력 조회."""
        if order_id:
            return [n for n in self._history if n.order_id == order_id]
        return list(self._history)

    def _send_to_channel(self, hub, channel: str, recipient: str, message: str) -> bool:
        """채널로 메시지 발송. NotificationHub 위임."""
        result = hub.dispatch('order_shipped', recipient, message)
        return bool(result)

    def _is_quiet_time(self, pref: NotificationPreference) -> bool:
        """현재 조용 시간 여부 확인."""
        now_hour = datetime.now(timezone.utc).hour
        start, end = pref.quiet_hours_start, pref.quiet_hours_end
        if start > end:
            return now_hour >= start or now_hour < end
        return start <= now_hour < end

    def _get_hub(self):
        if self._hub is None:
            from ..notifications.notification_hub import NotificationHub
            self._hub = NotificationHub()
        return self._hub
