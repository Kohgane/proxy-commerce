"""Slack 웹훅 연동 — Block Kit 포맷 메시지."""

import logging
import os

import requests

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')
SLACK_ENABLED = os.getenv('SLACK_ENABLED', '0') == '1'

_REQUEST_TIMEOUT = 10


class SlackNotifier:
    """Slack 웹훅을 통한 알림 발송.

    SLACK_WEBHOOK_URL, SLACK_ENABLED 환경변수로 설정.
    Block Kit 포맷 메시지 지원.
    """

    def __init__(self, webhook_url: str = None, enabled: bool = None):
        self._webhook_url = webhook_url or SLACK_WEBHOOK_URL
        self._enabled = enabled if enabled is not None else SLACK_ENABLED

    def send(self, text: str, blocks: list = None, username: str = 'Proxy Commerce Bot') -> bool:
        """Slack 메시지 발송.

        Args:
            text: 기본 텍스트 (알림/미리보기용)
            blocks: Block Kit 블록 리스트 (None이면 텍스트만)
            username: 봇 표시 이름

        Returns:
            발송 성공 여부
        """
        if not self._enabled:
            logger.debug("SlackNotifier 비활성화 — 메시지 건너뜀")
            return False
        if not self._webhook_url:
            logger.warning("SLACK_WEBHOOK_URL 미설정 — 메시지 건너뜀")
            return False

        payload = {
            'text': text,
            'username': username,
        }
        if blocks:
            payload['blocks'] = blocks

        try:
            resp = requests.post(self._webhook_url, json=payload, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            logger.info("Slack 메시지 발송 성공")
            return True
        except Exception as exc:
            logger.error("Slack 메시지 발송 실패: %s", exc)
            return False

    def send_order_alert(self, order: dict, event: str) -> bool:
        """주문 이벤트 Block Kit 알림.

        Args:
            order: 주문 데이터
            event: 'confirmed' | 'shipped' | 'delivered' | 'stale'
        """
        _ICONS = {
            'confirmed': '✅',
            'shipped': '🚚',
            'delivered': '📦',
            'stale': '⚠️',
        }
        icon = _ICONS.get(event, '🔔')
        order_id = order.get('order_id', '-')
        sku = order.get('sku', '-')
        status = order.get('status', '-')

        blocks = [
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': (
                        f"{icon} *주문 이벤트: {event}*\n"
                        f"주문번호: `{order_id}` | SKU: `{sku}` | 상태: `{status}`"
                    ),
                },
            }
        ]
        text = f"{icon} [{event}] 주문 {order_id}"
        return self.send(text=text, blocks=blocks)

    def send_error(self, error_msg: str, context: str = '') -> bool:
        """에러 알림 발송."""
        text = f"❌ 오류 발생: {error_msg}"
        blocks = [
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f"*❌ 오류 발생*\n```{error_msg}```\n_컨텍스트: {context}_",
                },
            }
        ]
        return self.send(text=text, blocks=blocks)
