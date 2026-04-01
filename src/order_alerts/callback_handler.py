"""텔레그램 콜백 쿼리 처리 모듈.

CallbackHandler는 Inline Keyboard 버튼 콜백 쿼리를 파싱하고 처리합니다.
"""

import logging

logger = logging.getLogger(__name__)

_ACTION_LABELS = {
    'approve': '주문이 승인되었습니다 ✅',
    'ship': '배송이 시작되었습니다 🚚',
    'cancel': '주문이 취소되었습니다 ❌',
}


class CallbackHandler:
    """텔레그램 Inline Keyboard 콜백 쿼리 처리 클래스."""

    def handle(self, callback_query: dict) -> dict:
        """텔레그램 콜백 쿼리 처리.

        callback_data 형식: "<action>:<order_id>" (예: "approve:ORDER-001")
        지원 액션: approve, ship, cancel

        Args:
            callback_query: 텔레그램 callback_query 딕셔너리

        Returns:
            처리 결과 딕셔너리:
                - action: 'approve' | 'ship' | 'cancel' | 'unknown'
                - order_id: 주문 ID 문자열
                - response_text: 사용자에게 표시할 응답 메시지
        """
        callback_data = callback_query.get('data', '')
        callback_id = callback_query.get('id', '')

        action, order_id = self._parse_callback_data(callback_data)

        response_text = _ACTION_LABELS.get(action, f"알 수 없는 액션: {callback_data}")

        logger.info(
            "콜백 처리 — callback_id=%s action=%s order_id=%s",
            callback_id,
            action,
            order_id,
        )

        return {
            'action': action,
            'order_id': order_id,
            'response_text': response_text,
        }

    # ── 내부 메서드 ──────────────────────────────────────────

    @staticmethod
    def _parse_callback_data(callback_data: str) -> tuple:
        """callback_data 파싱.

        Args:
            callback_data: '<action>:<order_id>' 형식 문자열

        Returns:
            (action, order_id) 튜플
        """
        if ':' in callback_data:
            action, _, order_id = callback_data.partition(':')
            return action.strip(), order_id.strip()
        return 'unknown', callback_data
