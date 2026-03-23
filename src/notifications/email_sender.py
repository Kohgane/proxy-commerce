"""SMTP 이메일 발송 — HTML + 텍스트 multipart, 재시도 로직."""

import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASS = os.getenv('SMTP_PASS', '')
SMTP_FROM_NAME = os.getenv('SMTP_FROM_NAME', 'Proxy Commerce')
SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', '')

MAX_RETRIES = 3
RETRY_DELAY = 2  # 초


class EmailSender:
    """SMTP 이메일 발송기.

    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS 환경변수로 설정.
    발송 실패 시 최대 3회 재시도.
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        user: str = None,
        password: str = None,
        from_name: str = None,
        from_email: str = None,
    ):
        self._host = host or SMTP_HOST
        self._port = port or SMTP_PORT
        self._user = user or SMTP_USER
        self._password = password or SMTP_PASS
        self._from_name = from_name or SMTP_FROM_NAME
        self._from_email = from_email or SMTP_FROM_EMAIL or self._user

    def send(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str = '',
        max_retries: int = MAX_RETRIES,
    ) -> bool:
        """이메일 발송 (재시도 포함).

        Args:
            to_email: 수신자 이메일
            subject: 제목
            html_body: HTML 본문
            text_body: 텍스트 대체 본문
            max_retries: 최대 재시도 횟수 (기본 3)

        Returns:
            발송 성공 여부
        """
        if not self._user or not self._password:
            logger.warning("SMTP 자격증명 미설정 — 이메일 발송 건너뜀")
            return False

        msg = self._build_message(to_email, subject, html_body, text_body)

        for attempt in range(1, max_retries + 1):
            try:
                self._smtp_send(msg, to_email)
                logger.info("이메일 발송 성공: %s (subject=%s)", to_email, subject)
                return True
            except Exception as exc:
                logger.warning(
                    "이메일 발송 시도 %d/%d 실패 (%s): %s",
                    attempt, max_retries, to_email, exc,
                )
                if attempt < max_retries:
                    time.sleep(RETRY_DELAY * attempt)

        logger.error("이메일 발송 최종 실패: %s", to_email)
        return False

    def _build_message(self, to_email: str, subject: str, html_body: str, text_body: str) -> MIMEMultipart:
        """MIMEMultipart 메시지 객체 생성."""
        msg = MIMEMultipart('alternative')
        from_header = f'{self._from_name} <{self._from_email}>'
        msg['From'] = from_header
        msg['To'] = to_email
        msg['Subject'] = subject

        if text_body:
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        return msg

    def _smtp_send(self, msg: MIMEMultipart, to_email: str) -> None:
        """SMTP 연결 후 메시지 발송."""
        with smtplib.SMTP(self._host, self._port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(self._user, self._password)
            server.sendmail(self._from_email, [to_email], msg.as_string())
