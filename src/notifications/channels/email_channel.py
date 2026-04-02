"""이메일 알림 채널."""

import logging

from ..notification_hub import NotificationChannel

logger = logging.getLogger(__name__)


class EmailChannel(NotificationChannel):
    """이메일 알림 채널 (SMTP mock)."""

    def __init__(self, smtp_host: str = 'localhost', smtp_port: int = 587,
                 username: str = '', password: str = ''):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self._sent: list = []

    def send(self, recipient: str, message: str, template_data: dict = None) -> bool:
        """이메일 발송 (SMTP mock).

        Args:
            recipient: 수신자 이메일
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
        logger.info("이메일 발송 (mock): %s", recipient)
        return True

    def get_sent(self) -> list:
        """발송 이력 반환."""
        return list(self._sent)
