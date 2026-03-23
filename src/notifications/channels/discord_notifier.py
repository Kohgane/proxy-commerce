"""Discord 웹훅 연동 — Embed 포맷 메시지."""

import logging
import os

import requests

logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')
DISCORD_ENABLED = os.getenv('DISCORD_ENABLED', '0') == '1'

_REQUEST_TIMEOUT = 10

# 이벤트별 색상 코드
_COLORS = {
    'confirmed': 0x2ECC71,   # 초록
    'shipped': 0x3498DB,     # 파랑
    'delivered': 0x9B59B6,   # 보라
    'error': 0xE74C3C,       # 빨강
    'warning': 0xF39C12,     # 주황
    'info': 0x95A5A6,        # 회색
}


class DiscordNotifier:
    """Discord 웹훅을 통한 알림 발송.

    DISCORD_WEBHOOK_URL, DISCORD_ENABLED 환경변수로 설정.
    Embed 포맷 메시지 지원.
    """

    def __init__(self, webhook_url: str = None, enabled: bool = None):
        self._webhook_url = webhook_url or DISCORD_WEBHOOK_URL
        self._enabled = enabled if enabled is not None else DISCORD_ENABLED

    def send(self, content: str = '', embeds: list = None, username: str = 'Proxy Commerce') -> bool:
        """Discord 메시지 발송.

        Args:
            content: 기본 텍스트
            embeds: Embed 리스트
            username: 웹훅 표시 이름

        Returns:
            발송 성공 여부
        """
        if not self._enabled:
            logger.debug("DiscordNotifier 비활성화 — 메시지 건너뜀")
            return False
        if not self._webhook_url:
            logger.warning("DISCORD_WEBHOOK_URL 미설정 — 메시지 건너뜀")
            return False

        payload = {'username': username}
        if content:
            payload['content'] = content
        if embeds:
            payload['embeds'] = embeds

        try:
            resp = requests.post(self._webhook_url, json=payload, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            logger.info("Discord 메시지 발송 성공")
            return True
        except Exception as exc:
            logger.error("Discord 메시지 발송 실패: %s", exc)
            return False

    def send_embed(
        self,
        title: str,
        description: str,
        color: int = None,
        fields: list = None,
        event_type: str = 'info',
    ) -> bool:
        """Embed 포맷 메시지 발송.

        Args:
            title: 임베드 제목
            description: 임베드 설명
            color: 색상 코드 (None이면 event_type에서 자동 선택)
            fields: [{'name': ..., 'value': ..., 'inline': bool}, ...]
            event_type: 'confirmed' | 'shipped' | 'delivered' | 'error' | 'warning' | 'info'
        """
        embed = {
            'title': title,
            'description': description,
            'color': color if color is not None else _COLORS.get(event_type, _COLORS['info']),
        }
        if fields:
            embed['fields'] = fields

        return self.send(embeds=[embed])

    def send_error(self, error_msg: str, context: str = '') -> bool:
        """에러 알림 발송."""
        fields = []
        if context:
            fields.append({'name': '컨텍스트', 'value': context, 'inline': False})
        return self.send_embed(
            title='❌ 오류 발생',
            description=f'```{error_msg}```',
            event_type='error',
            fields=fields,
        )

    def send_order_event(self, order: dict, event: str) -> bool:
        """주문 이벤트 Embed 알림."""
        _TITLES = {
            'confirmed': '✅ 주문 확인',
            'shipped': '🚚 배송 시작',
            'delivered': '📦 배송 완료',
        }
        title = _TITLES.get(event, f'🔔 주문 이벤트: {event}')
        order_id = order.get('order_id', '-')
        sku = order.get('sku', '-')
        fields = [
            {'name': '주문번호', 'value': str(order_id), 'inline': True},
            {'name': 'SKU', 'value': str(sku), 'inline': True},
        ]
        if order.get('tracking_number'):
            fields.append({'name': '운송장', 'value': order['tracking_number'], 'inline': True})

        return self.send_embed(
            title=title,
            description=f'주문 `{order_id}` 상태 업데이트',
            event_type=event,
            fields=fields,
        )
