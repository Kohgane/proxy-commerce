"""tests/test_customer_notifier.py — 고객 알림 테스트."""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

SAMPLE_ORDER = {
    'order_id': 'ORD-001',
    'customer_name': '홍길동',
    'customer_email': 'hong@example.com',
    'sku': 'PTR-TNK-001',
    'title': 'Tanker Briefcase',
    'sell_price_krw': 360000,
    'tracking_number': 'CJ123456',
    'carrier': 'cj',
}


# ══════════════════════════════════════════════════════════
# CustomerNotifier 테스트
# ══════════════════════════════════════════════════════════

class TestCustomerNotifier:
    def _make_notifier(self, enabled=True):
        mock_sender = MagicMock()
        mock_sender.send.return_value = True
        from src.notifications.customer_notifier import CustomerNotifier
        return CustomerNotifier(email_sender=mock_sender, enabled=enabled), mock_sender

    def test_notify_confirmed_enabled(self):
        notifier, sender = self._make_notifier(enabled=True)
        result = notifier.notify_confirmed(SAMPLE_ORDER)
        assert result is True
        sender.send.assert_called_once()

    def test_notify_confirmed_disabled(self):
        notifier, sender = self._make_notifier(enabled=False)
        result = notifier.notify_confirmed(SAMPLE_ORDER)
        assert result is False
        sender.send.assert_not_called()

    def test_notify_shipped(self):
        notifier, sender = self._make_notifier(enabled=True)
        result = notifier.notify_shipped(SAMPLE_ORDER)
        assert result is True
        sender.send.assert_called_once()

    def test_notify_delivered(self):
        notifier, sender = self._make_notifier(enabled=True)
        result = notifier.notify_delivered(SAMPLE_ORDER)
        assert result is True

    def test_no_email_returns_false(self):
        """이메일 없는 주문은 False 반환."""
        notifier, sender = self._make_notifier(enabled=True)
        order_no_email = {**SAMPLE_ORDER, 'customer_email': ''}
        result = notifier.notify_confirmed(order_no_email)
        assert result is False
        sender.send.assert_not_called()

    def test_sender_failure_returns_false(self):
        """이메일 발송 실패 시 False 반환."""
        mock_sender = MagicMock()
        mock_sender.send.return_value = False
        from src.notifications.customer_notifier import CustomerNotifier
        notifier = CustomerNotifier(email_sender=mock_sender, enabled=True)
        result = notifier.notify_confirmed(SAMPLE_ORDER)
        assert result is False

    def test_sender_exception_returns_false(self):
        """이메일 발송 예외 시 False 반환 (앱 크래시 없음)."""
        mock_sender = MagicMock()
        mock_sender.send.side_effect = Exception("SMTP error")
        from src.notifications.customer_notifier import CustomerNotifier
        notifier = CustomerNotifier(email_sender=mock_sender, enabled=True)
        result = notifier.notify_confirmed(SAMPLE_ORDER)
        assert result is False

    def test_english_locale(self):
        """영어 로케일로 알림 발송."""
        notifier, sender = self._make_notifier(enabled=True)
        result = notifier.notify_confirmed(SAMPLE_ORDER, locale='en')
        assert result is True


# ══════════════════════════════════════════════════════════
# 템플릿 테스트
# ══════════════════════════════════════════════════════════

class TestTemplates:
    def test_get_email_template_confirmed_ko(self):
        from src.notifications.templates import get_email_template
        subject, html, text = get_email_template('confirmed', SAMPLE_ORDER, locale='ko')
        assert 'ORD-001' in subject
        assert 'ORD-001' in html
        assert isinstance(text, str)

    def test_get_email_template_shipped_en(self):
        from src.notifications.templates import get_email_template
        subject, html, text = get_email_template('shipped', SAMPLE_ORDER, locale='en')
        assert 'Shipped' in subject or 'shipped' in subject.lower()
        assert isinstance(html, str)

    def test_get_email_template_delivered(self):
        from src.notifications.templates import get_email_template
        subject, html, text = get_email_template('delivered', SAMPLE_ORDER, locale='ko')
        assert isinstance(subject, str)

    def test_invalid_stage_raises(self):
        from src.notifications.templates import get_email_template
        with pytest.raises(ValueError):
            get_email_template('invalid_stage', SAMPLE_ORDER)

    def test_telegram_template(self):
        from src.notifications.templates import get_telegram_template
        text = get_telegram_template('confirmed', SAMPLE_ORDER)
        assert 'ORD-001' in text

    def test_template_missing_keys_safe(self):
        """키 누락된 주문도 안전하게 처리해야 한다."""
        from src.notifications.templates import get_email_template
        minimal_order = {'order_id': 'X-999', 'customer_email': 'x@y.com'}
        subject, html, text = get_email_template('confirmed', minimal_order, locale='ko')
        assert isinstance(subject, str)
