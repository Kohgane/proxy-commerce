"""src/shipping/notifications.py — 배송 상태 변경 알림."""
import logging
from typing import Optional

from .models import ShipmentRecord, ShipmentStatus

logger = logging.getLogger(__name__)


class ShippingNotifier:
    """배송 상태 변경 알림 전송."""

    def notify_status_change(
        self,
        record: ShipmentRecord,
        old_status: ShipmentStatus,
        order_id: Optional[str] = None,
    ) -> None:
        """상태 변경 시 Telegram 또는 로깅으로 알림."""
        message = (
            f"📦 배송 상태 변경\n"
            f"운송장: {record.tracking_number}\n"
            f"택배사: {record.carrier}\n"
            f"이전: {old_status.value} → 현재: {record.status.value}"
        )
        if order_id:
            message += f"\n주문 ID: {order_id}"

        sent = self._try_telegram(message)
        if not sent:
            logger.info("배송 알림: %s", message)

    def _try_telegram(self, message: str) -> bool:
        """Telegram 알림 전송 시도. 성공 시 True 반환."""
        try:
            from ..bot.telegram_sender import send_message  # type: ignore
            send_message(message)
            return True
        except Exception:
            return False
