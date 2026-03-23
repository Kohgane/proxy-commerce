"""tests/test_notification_hub.py — 멀티채널 알림 허브 테스트."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

SAMPLE_ORDER = {
    'order_id': 'ORD-100',
    'customer_name': '홍길동',
    'customer_email': 'hong@example.com',
    'sku': 'PTR-TNK-001',
    'tracking_number': 'CJ123456',
    'carrier': 'cj',
}


# ══════════════════════════════════════════════════════════
# NotificationHub 테스트
# ══════════════════════════════════════════════════════════

class TestNotificationHub:
    def _make_hub(self, telegram_token='testtoken', chat_id='12345'):
        mock_slack = MagicMock()
        mock_slack.send_order_alert.return_value = True
        mock_slack.send.return_value = True
        mock_slack.send_error.return_value = True

        mock_discord = MagicMock()
        mock_discord.send_error.return_value = True
        mock_discord.send.return_value = True

        mock_customer = MagicMock()
        mock_customer.notify_confirmed.return_value = True
        mock_customer.notify_shipped.return_value = True
        mock_customer.notify_delivered.return_value = True

        from src.notifications.hub import NotificationHub
        hub = NotificationHub(
            telegram_token=telegram_token,
            telegram_chat_id=chat_id,
            slack_notifier=mock_slack,
            discord_notifier=mock_discord,
            customer_notifier=mock_customer,
        )
        return hub, mock_slack, mock_discord, mock_customer

    def test_send_order_event_confirmed(self):
        hub, slack, discord, customer = self._make_hub()
        with patch.object(hub, '_send_telegram_order', return_value=True):
            results = hub.send_order_event(SAMPLE_ORDER, 'confirmed')
        assert 'slack' in results
        slack.send_order_alert.assert_called_once_with(SAMPLE_ORDER, 'confirmed')

    def test_send_order_event_shipped(self):
        hub, slack, discord, customer = self._make_hub()
        with patch.object(hub, '_send_telegram_order', return_value=True):
            results = hub.send_order_event(SAMPLE_ORDER, 'shipped')
        assert 'slack' in results

    def test_send_error_calls_discord_and_slack(self):
        hub, slack, discord, customer = self._make_hub()
        results = hub.send_error('Something went wrong', context='test_context')
        discord.send_error.assert_called_once()
        slack.send_error.assert_called_once()
        assert 'discord' in results
        assert 'slack' in results

    def test_send_custom_default_channels(self):
        hub, slack, discord, customer = self._make_hub()
        with patch.object(hub, '_send_telegram_raw', return_value=True):
            results = hub.send_custom('테스트 메시지')
        assert 'telegram' in results

    def test_send_custom_all_channels(self):
        hub, slack, discord, customer = self._make_hub()
        with patch.object(hub, '_send_telegram_raw', return_value=True):
            results = hub.send_custom('메시지', channels=['telegram', 'slack', 'discord'])
        assert 'telegram' in results
        assert 'slack' in results
        assert 'discord' in results

    def test_no_telegram_token_skips_telegram(self):
        hub, slack, discord, customer = self._make_hub(telegram_token='', chat_id='')
        results = hub.send_custom('메시지', channels=['telegram', 'slack'])
        assert results.get('telegram') is None or results.get('telegram') is False


# ══════════════════════════════════════════════════════════
# SlackNotifier 테스트
# ══════════════════════════════════════════════════════════

class TestSlackNotifier:
    def test_disabled_skips(self):
        from src.notifications.channels.slack_notifier import SlackNotifier
        notifier = SlackNotifier(webhook_url='https://hooks.slack.com/test', enabled=False)
        assert notifier.send('test') is False

    def test_no_url_skips(self):
        from src.notifications.channels.slack_notifier import SlackNotifier
        notifier = SlackNotifier(webhook_url='', enabled=True)
        assert notifier.send('test') is False

    def test_send_success(self):
        from src.notifications.channels.slack_notifier import SlackNotifier
        notifier = SlackNotifier(webhook_url='https://hooks.slack.com/test', enabled=True)
        with patch('src.notifications.channels.slack_notifier.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = MagicMock()
            result = notifier.send('test message')
        assert result is True

    def test_send_order_alert(self):
        from src.notifications.channels.slack_notifier import SlackNotifier
        notifier = SlackNotifier(webhook_url='https://hooks.slack.com/test', enabled=True)
        with patch.object(notifier, 'send', return_value=True):
            result = notifier.send_order_alert(SAMPLE_ORDER, 'confirmed')
        assert result is True


# ══════════════════════════════════════════════════════════
# DiscordNotifier 테스트
# ══════════════════════════════════════════════════════════

class TestDiscordNotifier:
    def test_disabled_skips(self):
        from src.notifications.channels.discord_notifier import DiscordNotifier
        notifier = DiscordNotifier(webhook_url='https://discord.com/api/webhooks/test', enabled=False)
        assert notifier.send('test') is False

    def test_no_url_skips(self):
        from src.notifications.channels.discord_notifier import DiscordNotifier
        notifier = DiscordNotifier(webhook_url='', enabled=True)
        assert notifier.send('test') is False

    def test_send_embed_success(self):
        from src.notifications.channels.discord_notifier import DiscordNotifier
        notifier = DiscordNotifier(webhook_url='https://discord.com/api/webhooks/test', enabled=True)
        with patch('src.notifications.channels.discord_notifier.requests.post') as mock_post:
            mock_post.return_value.status_code = 204
            mock_post.return_value.raise_for_status = MagicMock()
            result = notifier.send_embed(
                title='테스트',
                description='설명',
                event_type='info',
            )
        assert result is True

    def test_send_error(self):
        from src.notifications.channels.discord_notifier import DiscordNotifier
        notifier = DiscordNotifier(webhook_url='https://discord.com/api/webhooks/test', enabled=True)
        with patch.object(notifier, 'send_embed', return_value=True) as mock_embed:
            result = notifier.send_error('test error', context='unit test')
        assert result is True
        mock_embed.assert_called_once()

    def test_send_order_event(self):
        from src.notifications.channels.discord_notifier import DiscordNotifier
        notifier = DiscordNotifier(webhook_url='https://discord.com/api/webhooks/test', enabled=True)
        with patch.object(notifier, 'send_embed', return_value=True):
            result = notifier.send_order_event(SAMPLE_ORDER, 'shipped')
        assert result is True
