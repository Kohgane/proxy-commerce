"""텔레그램 알림 채널."""

import logging

from ..notification_hub import NotificationChannel

logger = logging.getLogger(__name__)


class TelegramChannel(NotificationChannel):
    """텔레그램 알림 채널 (mock)."""

    def __init__(self, bot_token: str = '', chat_id: str = ''):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._sent: list = []

    def send(self, recipient: str, message: str, template_data: dict = None) -> bool:
        """텔레그램 메시지 발송 (mock).

        Args:
            recipient: 수신자 (chat_id 또는 사용자명)
            message: 메시지 내용
            template_data: 추가 템플릿 데이터

        Returns:
            발송 성공 여부
        """
        target = recipient or self.chat_id
        record = {
            'recipient': target,
            'message': message,
            'template_data': template_data,
        }
        self._sent.append(record)
        logger.info("텔레그램 발송 (mock): %s", target)
        return True

    def get_sent(self) -> list:
        """발송 이력 반환."""
        return list(self._sent)
