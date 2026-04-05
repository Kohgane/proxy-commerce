"""src/vendor_marketplace/vendor_notifications.py — 판매자 알림 서비스 (Phase 98)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_NOTIFICATION_TEMPLATES = {
    'onboarding_approved': '🎉 [{name}] 판매자 신청이 승인되었습니다. 입점을 환영합니다!',
    'onboarding_rejected': '❌ [{name}] 판매자 신청이 거절되었습니다. 사유: {reason}',
    'settlement_completed': '💰 [{name}] 정산이 완료되었습니다. 정산액: {amount:,}원',
    'settlement_failed': '⚠️ [{name}] 정산 처리 중 오류가 발생했습니다. 사유: {reason}',
    'policy_change': '📢 [{name}] 플랫폼 정책이 변경되었습니다: {policy}',
    'violation_warning': '🚨 [{name}] 규정 위반 경고: {detail}',
    'product_approved': '✅ [{name}] 상품이 승인되어 판매 중입니다: {product_name}',
    'product_rejected': '❌ [{name}] 상품 심사 거절: {product_name} — 사유: {reason}',
    'low_stock': '📦 [{name}] 재고 부족 알림: {product_name} (잔여: {stock}개)',
    'suspension': '🔒 [{name}] 판매자 계정이 정지되었습니다. 사유: {reason}',
}


class VendorNotificationService:
    """판매자 알림 서비스 — 기존 NotificationHub 연동."""

    def __init__(self, notification_hub=None) -> None:
        self._hub = notification_hub
        self._history: List[dict] = []

    def _send(self, vendor_id: str, vendor_name: str, event: str, message: str, metadata: dict) -> dict:
        """알림 발송 (NotificationHub 연동 or 로컬 저장)."""
        record = {
            'notification_id': f'VN-{len(self._history) + 1:06d}',
            'vendor_id': vendor_id,
            'event': event,
            'message': message,
            'metadata': metadata,
            'sent_at': datetime.now(timezone.utc).isoformat(),
            'delivered': True,
        }
        self._history.append(record)

        if self._hub is not None:
            try:
                self._hub.send(
                    channel='vendor',
                    recipient=vendor_id,
                    message=message,
                    metadata=metadata,
                )
            except Exception as exc:
                logger.warning('NotificationHub 전송 실패: %s', exc)
                record['delivered'] = False
        else:
            logger.info('판매자 알림 [%s] %s: %s', event, vendor_id, message)

        return record

    def notify_approval(self, vendor_id: str, vendor_name: str) -> dict:
        msg = _NOTIFICATION_TEMPLATES['onboarding_approved'].format(name=vendor_name)
        return self._send(vendor_id, vendor_name, 'onboarding_approved', msg, {})

    def notify_rejection(self, vendor_id: str, vendor_name: str, reason: str = '') -> dict:
        msg = _NOTIFICATION_TEMPLATES['onboarding_rejected'].format(
            name=vendor_name, reason=reason or '심사 기준 미달'
        )
        return self._send(vendor_id, vendor_name, 'onboarding_rejected', msg, {'reason': reason})

    def notify_settlement_completed(
        self, vendor_id: str, vendor_name: str, amount: float
    ) -> dict:
        msg = _NOTIFICATION_TEMPLATES['settlement_completed'].format(
            name=vendor_name, amount=int(amount)
        )
        return self._send(
            vendor_id, vendor_name, 'settlement_completed', msg, {'amount': amount}
        )

    def notify_settlement_failed(
        self, vendor_id: str, vendor_name: str, reason: str = ''
    ) -> dict:
        msg = _NOTIFICATION_TEMPLATES['settlement_failed'].format(
            name=vendor_name, reason=reason or '시스템 오류'
        )
        return self._send(vendor_id, vendor_name, 'settlement_failed', msg, {'reason': reason})

    def notify_policy_change(
        self, vendor_id: str, vendor_name: str, policy: str
    ) -> dict:
        msg = _NOTIFICATION_TEMPLATES['policy_change'].format(
            name=vendor_name, policy=policy
        )
        return self._send(vendor_id, vendor_name, 'policy_change', msg, {'policy': policy})

    def notify_violation_warning(
        self, vendor_id: str, vendor_name: str, detail: str
    ) -> dict:
        msg = _NOTIFICATION_TEMPLATES['violation_warning'].format(
            name=vendor_name, detail=detail
        )
        return self._send(vendor_id, vendor_name, 'violation_warning', msg, {'detail': detail})

    def notify_product_approved(
        self, vendor_id: str, vendor_name: str, product_name: str
    ) -> dict:
        msg = _NOTIFICATION_TEMPLATES['product_approved'].format(
            name=vendor_name, product_name=product_name
        )
        return self._send(
            vendor_id, vendor_name, 'product_approved', msg, {'product_name': product_name}
        )

    def notify_product_rejected(
        self, vendor_id: str, vendor_name: str, product_name: str, reason: str = ''
    ) -> dict:
        msg = _NOTIFICATION_TEMPLATES['product_rejected'].format(
            name=vendor_name, product_name=product_name, reason=reason or '심사 기준 미달'
        )
        return self._send(
            vendor_id, vendor_name, 'product_rejected', msg,
            {'product_name': product_name, 'reason': reason}
        )

    def notify_low_stock(
        self, vendor_id: str, vendor_name: str, product_name: str, stock: int
    ) -> dict:
        msg = _NOTIFICATION_TEMPLATES['low_stock'].format(
            name=vendor_name, product_name=product_name, stock=stock
        )
        return self._send(
            vendor_id, vendor_name, 'low_stock', msg,
            {'product_name': product_name, 'stock': stock}
        )

    def notify_suspension(
        self, vendor_id: str, vendor_name: str, reason: str = ''
    ) -> dict:
        msg = _NOTIFICATION_TEMPLATES['suspension'].format(
            name=vendor_name, reason=reason or '규정 위반'
        )
        return self._send(vendor_id, vendor_name, 'suspension', msg, {'reason': reason})

    def get_history(
        self, vendor_id: Optional[str] = None, event: Optional[str] = None
    ) -> List[dict]:
        """알림 이력 조회."""
        history = self._history
        if vendor_id:
            history = [h for h in history if h['vendor_id'] == vendor_id]
        if event:
            history = [h for h in history if h['event'] == event]
        return history
