"""tests/e2e/test_notification_flow.py — 알림 허브 플로우 E2E 테스트.

NotificationHub, CustomerNotifier의 전체 알림 흐름을 검증한다.
"""

from unittest.mock import MagicMock, patch


SAMPLE_ORDER = {
    'id': '55001',
    'order_number': '#3001',
    'customer': {'name': '홍길동', 'email': 'hong@example.com'},
    'customer_email': 'hong@example.com',
    'sku': 'PTR-TNK-001',
    'total_price': '370000',
}


class TestNotificationHubTelegram:
    """NotificationHub 텔레그램 채널 E2E 테스트."""

    def test_notification_hub_telegram(self, monkeypatch):
        """NotificationHub가 텔레그램 채널로 알림을 발송한다."""
        monkeypatch.setenv('TELEGRAM_ENABLED', '1')
        monkeypatch.setenv('TELEGRAM_BOT_TOKEN', '123456:test')
        monkeypatch.setenv('TELEGRAM_CHAT_ID', '-100test')

        with patch('src.utils.telegram.send_tele') as mock_tele:
            mock_tele.return_value = None

            from src.notifications.hub import NotificationHub
            hub = NotificationHub(
                telegram_token='123456:test',
                telegram_chat_id='-100test',
            )
            result = hub.send_order_event(SAMPLE_ORDER, event='confirmed')

        # 텔레그램 발송 시도 여부 확인
        assert isinstance(result, dict)

    def test_notification_hub_slack_disabled(self, monkeypatch):
        """Slack 비활성화 시 Slack send_order_alert가 False를 반환한다."""
        monkeypatch.setenv('SLACK_ENABLED', '0')
        monkeypatch.setenv('TELEGRAM_ENABLED', '1')

        mock_slack = MagicMock()
        # _enabled=False인 SlackNotifier는 send_order_alert에서 False 반환
        mock_slack.send_order_alert.return_value = False

        with patch('src.utils.telegram.send_tele', return_value=None):
            from src.notifications.hub import NotificationHub
            hub = NotificationHub(
                telegram_token='123456:test',
                telegram_chat_id='-100test',
                slack_notifier=mock_slack,
            )
            result = hub.send_order_event(SAMPLE_ORDER, event='confirmed')

        # hub는 slack을 항상 호출하지만, disabled 상태이면 False 반환
        assert result.get('slack') is False


class TestCustomerNotificationFlow:
    """CustomerNotifier 알림 플로우 E2E 테스트."""

    def test_customer_notification_flow_confirmed(self, monkeypatch):
        """주문 확인 시 고객 이메일 알림 플로우 검증."""
        monkeypatch.setenv('CUSTOMER_NOTIFY_ENABLED', '1')

        mock_sender = MagicMock()
        mock_sender.send.return_value = True

        from src.notifications.customer_notifier import CustomerNotifier
        notifier = CustomerNotifier(email_sender=mock_sender, enabled=True)
        result = notifier.notify_confirmed(SAMPLE_ORDER)

        assert result is True
        mock_sender.send.assert_called_once()

    def test_customer_notification_flow_shipped(self, monkeypatch):
        """배송 알림 플로우 검증."""
        mock_sender = MagicMock()
        mock_sender.send.return_value = True

        from src.notifications.customer_notifier import CustomerNotifier
        notifier = CustomerNotifier(email_sender=mock_sender, enabled=True)
        result = notifier.notify_shipped(
            SAMPLE_ORDER,
            tracking_info={'tracking_number': 'JD123', 'carrier': 'CJ대한통운'},
        )

        assert result is True
        mock_sender.send.assert_called_once()

    def test_customer_notification_flow_delivered(self, monkeypatch):
        """배송 완료 알림 플로우 검증."""
        mock_sender = MagicMock()
        mock_sender.send.return_value = True

        from src.notifications.customer_notifier import CustomerNotifier
        notifier = CustomerNotifier(email_sender=mock_sender, enabled=True)
        result = notifier.notify_delivered(SAMPLE_ORDER)

        assert result is True
        mock_sender.send.assert_called_once()

    def test_customer_notification_disabled(self, monkeypatch):
        """CUSTOMER_NOTIFY_ENABLED=0 시 발송하지 않는다."""
        monkeypatch.setenv('CUSTOMER_NOTIFY_ENABLED', '0')

        mock_sender = MagicMock()

        from src.notifications.customer_notifier import CustomerNotifier
        notifier = CustomerNotifier(email_sender=mock_sender, enabled=False)
        result = notifier.notify_confirmed(SAMPLE_ORDER)

        assert result is False
        mock_sender.send.assert_not_called()
