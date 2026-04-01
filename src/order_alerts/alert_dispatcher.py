"""텔레그램 주문 알림 발송 모듈.

주문 정보를 텔레그램 메시지로 포맷팅하여 발송합니다.
"""

import logging
import os
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = 'https://api.telegram.org/bot{token}'
_SEND_MESSAGE_PATH = '/sendMessage'
_REQUEST_TIMEOUT = 10

_PLATFORM_EMOJI = {
    'coupang': '🛒',
    'naver': '🟢',
}

_STATUS_LABEL = {
    'ACCEPT': '주문접수',
    'INSTRUCT': '발주확인',
    'DEPARTURE': '배송시작',
    'DELIVERING': '배송중',
    'DELIVERED': '배송완료',
    'CANCEL_REQUEST': '취소요청',
    'CANCELED': '주문취소',
    'RETURN_REQUEST': '반품요청',
    'RETURNED': '반품완료',
    'PAY_WAITING': '결제대기',
    'PAYED': '결제완료',
    'PURCHASE_DECIDED': '구매확정',
}


class AlertDispatcher:
    """텔레그램 주문 알림 발송 클래스.

    환경변수:
        ORDER_ALERT_TELEGRAM_BOT_TOKEN: 텔레그램 봇 토큰
        ORDER_ALERT_TELEGRAM_CHAT_ID: 텔레그램 채팅/채널 ID
    """

    def __init__(
        self,
        bot_token: str = None,
        chat_id: str = None,
    ):
        """초기화.

        Args:
            bot_token: 텔레그램 봇 토큰 (None이면 환경변수 사용)
            chat_id: 텔레그램 채팅 ID (None이면 환경변수 사용)
        """
        self._bot_token = bot_token or os.getenv('ORDER_ALERT_TELEGRAM_BOT_TOKEN', '')
        self._chat_id = chat_id or os.getenv('ORDER_ALERT_TELEGRAM_CHAT_ID', '')

    # ── public API ───────────────────────────────────────────

    def send_new_order_alert(self, order: dict) -> bool:
        """신규 주문 알림 발송.

        Args:
            order: 정규화된 주문 딕셔너리

        Returns:
            발송 성공 여부
        """
        message = self._format_new_order_message(order)
        return self._send_message(message)

    def send_status_change_alert(self, order: dict, new_status: str) -> bool:
        """주문 상태 변경 알림 발송.

        Args:
            order: 정규화된 주문 딕셔너리
            new_status: 새로운 주문 상태 코드

        Returns:
            발송 성공 여부
        """
        message = self._format_status_change_message(order, new_status)
        return self._send_message(message)

    def send_bulk_alerts(self, orders: List[dict]) -> int:
        """다수 주문 알림 일괄 발송.

        Args:
            orders: 정규화된 주문 목록

        Returns:
            성공적으로 발송된 알림 수
        """
        success_count = 0
        for order in orders:
            if self.send_new_order_alert(order):
                success_count += 1
        return success_count

    def send_custom_message(self, text: str) -> bool:
        """커스텀 텍스트 메시지 발송.

        Args:
            text: 발송할 메시지 텍스트

        Returns:
            발송 성공 여부
        """
        return self._send_message(text)

    # ── 메시지 포맷팅 ────────────────────────────────────────

    def _format_new_order_message(self, order: dict) -> str:
        """신규 주문 알림 메시지 포맷팅.

        Args:
            order: 정규화된 주문 딕셔너리

        Returns:
            포맷팅된 텔레그램 메시지
        """
        platform = order.get('platform', 'unknown')
        emoji = _PLATFORM_EMOJI.get(platform, '📦')
        platform_label = '쿠팡' if platform == 'coupang' else '네이버 스마트스토어'

        order_number = order.get('order_number', order.get('order_id', 'N/A'))
        product_names = order.get('product_names', [])
        quantities = order.get('quantities', [])
        total_price = order.get('total_price', 0)
        buyer_name = order.get('buyer_name', '')
        buyer_phone = order.get('buyer_phone', '')
        created_at = order.get('created_at', '')

        # 상품 목록 포맷
        items_text = ''
        for name, qty in zip(product_names, quantities):
            items_text += f'  • {name} × {qty}\n'
        if not items_text:
            items_text = '  • (상품 정보 없음)\n'

        price_str = f"{int(total_price):,}원" if total_price else 'N/A'
        phone_masked = self._mask_phone(buyer_phone)

        lines = [
            f"{emoji} *[{platform_label}] 신규 주문 접수*",
            "",
            f"📋 주문번호: `{order_number}`",
            "🛍 상품:",
            items_text.rstrip(),
            f"💰 결제금액: {price_str}",
            f"👤 구매자: {buyer_name}",
            f"📱 연락처: {phone_masked}",
        ]
        if created_at:
            lines.append(f"🕐 주문시각: {created_at[:19].replace('T', ' ')}")

        return '\n'.join(lines)

    def _format_status_change_message(self, order: dict, new_status: str) -> str:
        """주문 상태 변경 알림 메시지 포맷팅.

        Args:
            order: 정규화된 주문 딕셔너리
            new_status: 새로운 주문 상태 코드

        Returns:
            포맷팅된 텔레그램 메시지
        """
        platform = order.get('platform', 'unknown')
        emoji = _PLATFORM_EMOJI.get(platform, '📦')
        platform_label = '쿠팡' if platform == 'coupang' else '네이버 스마트스토어'
        order_number = order.get('order_number', order.get('order_id', 'N/A'))
        status_label = _STATUS_LABEL.get(new_status, new_status)

        status_emoji = {
            'DELIVERING': '🚚',
            'DELIVERED': '✅',
            'CANCELED': '❌',
            'RETURNED': '🔄',
        }.get(new_status, '📌')

        lines = [
            f"{emoji} *[{platform_label}] 주문 상태 변경*",
            "",
            f"📋 주문번호: `{order_number}`",
            f"{status_emoji} 상태: *{status_label}*",
        ]
        return '\n'.join(lines)

    # ── 텔레그램 API ─────────────────────────────────────────

    def _send_message(self, text: str) -> bool:
        """텔레그램 메시지 발송.

        Args:
            text: 발송할 메시지

        Returns:
            발송 성공 여부
        """
        if not self._bot_token or not self._chat_id:
            logger.warning("텔레그램 토큰/채팅ID 미설정 — 알림 발송 건너뜀")
            return False

        url = f"https://api.telegram.org/bot{self._bot_token}{_SEND_MESSAGE_PATH}"
        payload = {
            'chat_id': self._chat_id,
            'text': text,
            'parse_mode': 'Markdown',
        }
        try:
            resp = requests.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            logger.info("텔레그램 알림 발송 완료 (chat_id=%s)", self._chat_id)
            return True
        except requests.exceptions.RequestException as exc:
            logger.error("텔레그램 알림 발송 실패: %s", exc)
            return False

    # ── 유틸리티 ────────────────────────────────────────────

    @staticmethod
    def _mask_phone(phone: str) -> str:
        """전화번호 마스킹 (뒤 4자리 제외).

        Args:
            phone: 전화번호 문자열

        Returns:
            마스킹된 전화번호 (예: 010-****-1234)
        """
        if not phone:
            return '(미공개)'
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) >= 8:
            return f"{digits[:3]}-****-{digits[-4:]}"
        return '*' * len(phone)

    @property
    def is_configured(self) -> bool:
        """알림 발송 설정 완료 여부."""
        return bool(self._bot_token and self._chat_id)

    def get_bot_token(self) -> Optional[str]:
        """봇 토큰 반환 (설정된 경우)."""
        return self._bot_token or None

    def get_chat_id(self) -> Optional[str]:
        """채팅 ID 반환 (설정된 경우)."""
        return self._chat_id or None
