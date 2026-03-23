"""tests/test_email_sender.py — 이메일 발송 테스트."""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ══════════════════════════════════════════════════════════
# EmailSender 테스트
# ══════════════════════════════════════════════════════════

class TestEmailSender:
    def _make_sender(self, **kwargs):
        from src.notifications.email_sender import EmailSender
        defaults = {
            'host': 'smtp.example.com',
            'port': 587,
            'user': 'test@example.com',
            'password': 'test_pass',
            'from_name': 'Test',
            'from_email': 'test@example.com',
        }
        defaults.update(kwargs)
        return EmailSender(**defaults)

    def test_send_success(self):
        """정상 발송 시 True 반환."""
        sender = self._make_sender()
        with patch.object(sender, '_smtp_send') as mock_smtp:
            result = sender.send(
                to_email='recipient@example.com',
                subject='테스트',
                html_body='<p>테스트</p>',
                text_body='테스트',
            )
        assert result is True
        mock_smtp.assert_called_once()

    def test_send_retry_on_failure(self):
        """발송 실패 시 최대 3회 재시도."""
        sender = self._make_sender()
        with patch.object(sender, '_smtp_send', side_effect=Exception("Connection refused")):
            with patch('src.notifications.email_sender.time.sleep'):
                result = sender.send(
                    to_email='recipient@example.com',
                    subject='테스트',
                    html_body='<p>테스트</p>',
                    max_retries=3,
                )
        assert result is False

    def test_send_succeeds_on_second_attempt(self):
        """첫 번째 시도 실패 후 두 번째 시도 성공."""
        sender = self._make_sender()
        call_count = {'n': 0}

        def side_effect(*args, **kwargs):
            call_count['n'] += 1
            if call_count['n'] < 2:
                raise Exception("Temporary error")

        with patch.object(sender, '_smtp_send', side_effect=side_effect):
            with patch('src.notifications.email_sender.time.sleep'):
                result = sender.send(
                    to_email='recipient@example.com',
                    subject='테스트',
                    html_body='<p>테스트</p>',
                    max_retries=3,
                )
        assert result is True

    def test_no_credentials_returns_false(self):
        """자격증명 없으면 False 반환."""
        from src.notifications.email_sender import EmailSender
        sender = EmailSender(host='smtp.example.com', port=587, user='', password='')
        result = sender.send('x@y.com', 'subj', '<p>body</p>')
        assert result is False

    def test_build_message(self):
        """MIMEMultipart 메시지 구조 검증."""
        sender = self._make_sender()
        msg = sender._build_message('to@x.com', 'Test Subject', '<p>html</p>', 'text')
        assert msg['Subject'] == 'Test Subject'
        assert msg['To'] == 'to@x.com'

    def test_build_message_html_only(self):
        """텍스트 없이 HTML만 있는 메시지."""
        sender = self._make_sender()
        msg = sender._build_message('to@x.com', 'Subj', '<p>html</p>', '')
        assert msg['Subject'] == 'Subj'
