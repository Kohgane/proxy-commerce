"""슬랙 알림 채널."""

import logging

from ..notification_hub import NotificationChannel

logger = logging.getLogger(__name__)


class SlackChannel(NotificationChannel):
    """슬랙 알림 채널 (Webhook mock)."""

    def __init__(self, webhook_url: str = ''):
        self.webhook_url = webhook_url
        self._sent: list = []

    def send(self, recipient: str, message: str, template_data: dict = None) -> bool:
        """슬랙 메시지 발송 (Webhook mock).

        Args:
            recipient: 채널명 또는 사용자명
            message: 메시지 내용
            template_data: 추가 템플릿 데이터

        Returns:
            발송 성공 여부
        """
        record = {
            'recipient': recipient,
            'message': message,
            'template_data': template_data,
        }
        self._sent.append(record)
        logger.info("슬랙 발송 (mock): %s", recipient)
        return True

    def get_sent(self) -> list:
        """발송 이력 반환."""
        return list(self._sent)
