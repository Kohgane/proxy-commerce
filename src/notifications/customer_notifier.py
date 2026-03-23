"""고객 알림 관리자 — 주문 확인/배송 알림."""

import logging
import os

logger = logging.getLogger(__name__)

CUSTOMER_NOTIFY_ENABLED = os.getenv('CUSTOMER_NOTIFY_ENABLED', '0') == '1'


class CustomerNotifier:
    """고객 알림 관리자.

    CUSTOMER_NOTIFY_ENABLED=1 환경변수로 활성화.
    이메일 발송은 EmailSender를 통해 처리.
    """

    STAGE_CONFIRMED = 'confirmed'
    STAGE_SHIPPED = 'shipped'
    STAGE_DELIVERED = 'delivered'

    def __init__(self, email_sender=None, enabled: bool = None):
        """
        email_sender: EmailSender 인스턴스 (None이면 자동 생성)
        enabled: True/False (None이면 환경변수 사용)
        """
        self._enabled = enabled if enabled is not None else CUSTOMER_NOTIFY_ENABLED
        self._email_sender = email_sender

    def _get_sender(self):
        """EmailSender 인스턴스 반환 (지연 초기화)."""
        if self._email_sender is None:
            from .email_sender import EmailSender
            self._email_sender = EmailSender()
        return self._email_sender

    # ── 공개 API ────────────────────────────────────────────

    def notify_confirmed(self, order: dict, locale: str = 'ko') -> bool:
        """주문 확인 알림 발송.

        Args:
            order: 주문 데이터 딕셔너리
            locale: 언어 코드 ('ko' | 'en')

        Returns:
            발송 성공 여부
        """
        if not self._enabled:
            logger.debug("CustomerNotifier 비활성화 — 주문 확인 알림 건너뜀")
            return False
        return self._send(order, self.STAGE_CONFIRMED, locale)

    def notify_shipped(self, order: dict, tracking_info: dict = None, locale: str = 'ko') -> bool:
        """배송 시작 알림 발송.

        Args:
            order: 주문 데이터 딕셔너리
            tracking_info: {'tracking_number': ..., 'carrier': ...}
            locale: 언어 코드
        """
        if not self._enabled:
            logger.debug("CustomerNotifier 비활성화 — 배송 알림 건너뜀")
            return False
        if tracking_info:
            order = {**order, **tracking_info}
        return self._send(order, self.STAGE_SHIPPED, locale)

    def notify_delivered(self, order: dict, locale: str = 'ko') -> bool:
        """배송 완료 알림 발송."""
        if not self._enabled:
            logger.debug("CustomerNotifier 비활성화 — 배송완료 알림 건너뜀")
            return False
        return self._send(order, self.STAGE_DELIVERED, locale)

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _send(self, order: dict, stage: str, locale: str) -> bool:
        """알림 발송 공통 로직."""
        from .templates import get_email_template
        email = order.get('customer_email', '')
        if not email:
            logger.warning("고객 이메일 없음 — 알림 건너뜀 (order_id=%s)", order.get('order_id', '-'))
            return False

        try:
            subject, html_body, text_body = get_email_template(stage, order, locale)
            sender = self._get_sender()
            return sender.send(
                to_email=email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )
        except Exception as exc:
            logger.error("알림 발송 실패 (stage=%s, order_id=%s): %s", stage, order.get('order_id', '-'), exc)
            return False
