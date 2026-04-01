"""텔레그램 알림 발송 모듈 (Phase 21).

TelegramNotifier는 Inline Keyboard를 포함한 주문 알림 메시지를 발송합니다.
"""

import logging
import os

import requests

from .templates import render_for_status

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = 'https://api.telegram.org/bot{token}'
_SEND_MESSAGE_PATH = '/sendMessage'
_REQUEST_TIMEOUT = 10


class TelegramNotifier:
    """텔레그램 주문 알림 발송 클래스 (Inline Keyboard 지원).

    환경변수:
        ORDER_ALERT_TELEGRAM_BOT_TOKEN: 텔레그램 봇 토큰
        ORDER_ALERT_TELEGRAM_CHAT_ID: 텔레그램 채팅/채널 ID
    """

    def __init__(self, bot_token: str = None, chat_id: str = None):
        """초기화.

        Args:
            bot_token: 텔레그램 봇 토큰 (None이면 환경변수 사용)
            chat_id: 텔레그램 채팅 ID (None이면 환경변수 사용)
        """
        self._bot_token = bot_token or os.getenv('ORDER_ALERT_TELEGRAM_BOT_TOKEN', '')
        self._chat_id = chat_id or os.getenv('ORDER_ALERT_TELEGRAM_CHAT_ID', '')

    # ── public API ───────────────────────────────────────────

    def send_message(self, text: str, reply_markup: dict = None) -> bool:
        """텔레그램 메시지 발송.

        Args:
            text: 발송할 메시지 텍스트
            reply_markup: 인라인 키보드 등 reply_markup 딕셔너리 (선택)

        Returns:
            발송 성공 여부
        """
        if not self._bot_token or not self._chat_id:
            logger.warning("텔레그램 토큰/채팅ID 미설정 — 알림 발송 건너뜀")
            return False

        url = _TELEGRAM_API_BASE.format(token=self._bot_token) + _SEND_MESSAGE_PATH
        payload: dict = {
            'chat_id': self._chat_id,
            'text': text,
            'parse_mode': 'Markdown',
        }
        if reply_markup is not None:
            payload['reply_markup'] = reply_markup

        try:
            resp = requests.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            logger.info("텔레그램 알림 발송 완료 (chat_id=%s)", self._chat_id)
            return True
        except requests.exceptions.RequestException as exc:
            logger.error("텔레그램 알림 발송 실패: %s", exc)
            return False

    def build_order_inline_keyboard(self, order_id: str) -> dict:
        """주문 관리용 Inline Keyboard 생성.

        Args:
            order_id: 주문 ID 문자열

        Returns:
            텔레그램 inline_keyboard reply_markup 딕셔너리
        """
        return {
            'inline_keyboard': [
                [
                    {'text': '✅ 주문 승인', 'callback_data': f'approve:{order_id}'},
                    {'text': '🚚 배송 시작', 'callback_data': f'ship:{order_id}'},
                    {'text': '❌ 주문 취소', 'callback_data': f'cancel:{order_id}'},
                ]
            ]
        }

    def send_order_alert(self, order: dict, status: str) -> bool:
        """주문 상태에 맞는 알림을 Inline Keyboard와 함께 발송.

        Args:
            order: 정규화된 주문 딕셔너리
            status: 주문 상태 코드

        Returns:
            발송 성공 여부
        """
        text = render_for_status(order, status)
        order_id = order.get('order_id', '')
        keyboard = self.build_order_inline_keyboard(order_id) if order_id else None
        return self.send_message(text, reply_markup=keyboard)

    @property
    def is_configured(self) -> bool:
        """알림 발송 설정 완료 여부."""
        return bool(self._bot_token and self._chat_id)
