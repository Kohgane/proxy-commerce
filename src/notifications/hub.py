"""통합 알림 허브 — 텔레그램 + Slack + Discord + 이메일 통합 발송."""

import logging
import os

logger = logging.getLogger(__name__)

# 채널별 활성화 여부 (개별 모듈 환경변수에서 읽음)
_TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', '1') == '1'
_CUSTOMER_NOTIFY_ENABLED = os.getenv('CUSTOMER_NOTIFY_ENABLED', '0') == '1'

# 알림 유형별 채널 매핑
# - order: 텔레그램 + Slack
# - error: Discord (+ Slack)
# - customer: 이메일
_CHANNEL_MAP = {
    'order': ['telegram', 'slack'],
    'error': ['discord', 'slack'],
    'customer': ['email'],
    'all': ['telegram', 'slack', 'discord', 'email'],
}


class NotificationHub:
    """통합 알림 허브.

    채널별 활성화/비활성화 설정 + 알림 유형별 채널 매핑.
    """

    def __init__(
        self,
        telegram_token: str = None,
        telegram_chat_id: str = None,
        slack_notifier=None,
        discord_notifier=None,
        customer_notifier=None,
    ):
        """
        각 채널 인스턴스를 주입하거나, None이면 지연 초기화.
        """
        self._telegram_token = telegram_token or os.getenv('TELEGRAM_BOT_TOKEN', '')
        self._telegram_chat_id = telegram_chat_id or os.getenv('TELEGRAM_CHAT_ID', '')
        self._slack = slack_notifier
        self._discord = discord_notifier
        self._customer = customer_notifier

    # ── 채널 접근자 ─────────────────────────────────────────

    def _get_slack(self):
        if self._slack is None:
            from .channels.slack_notifier import SlackNotifier
            self._slack = SlackNotifier()
        return self._slack

    def _get_discord(self):
        if self._discord is None:
            from .channels.discord_notifier import DiscordNotifier
            self._discord = DiscordNotifier()
        return self._discord

    def _get_customer(self):
        if self._customer is None:
            from .customer_notifier import CustomerNotifier
            self._customer = CustomerNotifier()
        return self._customer

    # ── 공개 API ────────────────────────────────────────────

    def send_order_event(self, order: dict, event: str, locale: str = 'ko') -> dict:
        """주문 이벤트 알림 — 텔레그램 + Slack.

        Args:
            order: 주문 데이터
            event: 'confirmed' | 'shipped' | 'delivered'
            locale: 고객 이메일 언어

        Returns:
            채널별 성공 여부 딕셔너리
        """
        results = {}

        # 텔레그램 (운영자 알림)
        if _TELEGRAM_ENABLED and self._telegram_token:
            results['telegram'] = self._send_telegram_order(order, event)

        # Slack
        results['slack'] = self._get_slack().send_order_alert(order, event)

        # 고객 이메일
        if _CUSTOMER_NOTIFY_ENABLED:
            customer = self._get_customer()
            if event == 'confirmed':
                results['email'] = customer.notify_confirmed(order, locale)
            elif event == 'shipped':
                results['email'] = customer.notify_shipped(order, locale=locale)
            elif event == 'delivered':
                results['email'] = customer.notify_delivered(order, locale)

        return results

    def send_error(self, error_msg: str, context: str = '') -> dict:
        """에러 알림 — Discord + Slack.

        Returns:
            채널별 성공 여부 딕셔너리
        """
        results = {}
        results['discord'] = self._get_discord().send_error(error_msg, context)
        results['slack'] = self._get_slack().send_error(error_msg, context)
        return results

    def send_custom(self, message: str, channels: list = None) -> dict:
        """커스텀 메시지를 지정 채널에 발송.

        Args:
            message: 발송할 메시지
            channels: ['telegram', 'slack', 'discord'] (None이면 telegram만)

        Returns:
            채널별 성공 여부 딕셔너리
        """
        if channels is None:
            channels = ['telegram']

        results = {}
        if 'telegram' in channels and _TELEGRAM_ENABLED and self._telegram_token:
            results['telegram'] = self._send_telegram_raw(message)
        if 'slack' in channels:
            results['slack'] = self._get_slack().send(text=message)
        if 'discord' in channels:
            results['discord'] = self._get_discord().send(content=message)
        return results

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _send_telegram_order(self, order: dict, event: str) -> bool:
        """텔레그램 주문 이벤트 알림."""
        from .templates import get_telegram_template
        try:
            text = get_telegram_template(event, order)
            return self._send_telegram_raw(text)
        except Exception as exc:
            logger.error("텔레그램 주문 알림 실패: %s", exc)
            return False

    def _send_telegram_raw(self, text: str) -> bool:
        """텔레그램 raw 메시지 발송."""
        import requests as req_lib
        if not self._telegram_token or not self._telegram_chat_id:
            return False
        url = f'https://api.telegram.org/bot{self._telegram_token}/sendMessage'
        try:
            resp = req_lib.post(
                url,
                json={'chat_id': self._telegram_chat_id, 'text': text, 'parse_mode': 'Markdown'},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("텔레그램 메시지 발송 실패: %s", exc)
            return False
