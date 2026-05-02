"""src/returns_automation/refund_orchestrator.py — Phase 118: 환불 자동 처리 오케스트레이터.

PG 환불 호출 (mock) + 포인트/쿠폰 환원 + NotificationHub 알림.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from .models import AutoReturnRequest, ReturnDecision

logger = logging.getLogger(__name__)


class RefundOrchestrator:
    """환불 자동 처리 오케스트레이터.

    process_refund() 메서드로 환불 전 과정을 자동 처리한다.
    """

    def process_refund(
        self,
        request: AutoReturnRequest,
        decision: ReturnDecision,
        pg_method: str = 'card',
        use_points: bool = False,
    ) -> dict:
        """환불 자동 처리.

        1. PG 환불 호출 (mock)
        2. 포인트/쿠폰 환원 (src/points/ 연동 시도)
        3. 환불 알림 (NotificationHub: payment_refunded)

        Args:
            request: 반품 요청 객체
            decision: 반품 처리 결정 객체
            pg_method: 결제 방법 (card/bank/virtual_account)
            use_points: 적립금 전환 여부

        Returns:
            환불 처리 결과 dict
        """
        refund_amount = decision.refund_amount
        result = {
            'request_id': request.request_id,
            'order_id': request.order_id,
            'user_id': request.user_id,
            'refund_amount': str(refund_amount),
            'pg_method': pg_method,
            'status': 'success',
            'pg_result': None,
            'points_restored': False,
            'notification_sent': False,
        }

        # 1. PG 환불 (mock 또는 실제 payment_gateway 연동)
        pg_result = self._call_pg_refund(request.order_id, refund_amount, pg_method)
        result['pg_result'] = pg_result

        # 2. 포인트/쿠폰 환원
        if use_points or pg_method == 'points':
            points_result = self._restore_points(request.user_id, refund_amount)
            result['points_restored'] = points_result

        # 3. 환불 알림 발송
        notified = self._send_refund_notification(request, refund_amount)
        result['notification_sent'] = notified

        logger.info(
            "[환불] %s 처리 완료: %s원 (PG: %s)",
            request.request_id,
            refund_amount,
            pg_method,
        )
        return result

    def process_partial_refund(
        self,
        request: AutoReturnRequest,
        partial_amount: Decimal,
        reason: str = '',
    ) -> dict:
        """부분 환불 처리.

        Args:
            request: 반품 요청 객체
            partial_amount: 부분 환불 금액
            reason: 부분 환불 사유
        """
        decision = ReturnDecision(
            decision='approved',
            refund_amount=partial_amount,
            notes=f'부분 환불: {reason}',
        )
        result = self.process_refund(request, decision)
        result['partial_refund'] = True
        result['partial_reason'] = reason
        logger.info("[환불] %s 부분 환불: %s원", request.request_id, partial_amount)
        return result

    # ── 내부 헬퍼 ─────────────────────────────────────────

    def _call_pg_refund(self, order_id: str, amount: Decimal, method: str) -> dict:
        """PG 환불 호출 (mock).

        실 운영 시 src/payment_gateway/ 또는 src/payment_recovery/ 연동.
        """
        try:
            from ..payment_gateway.gateway import PaymentGateway
            gw = PaymentGateway()
            return gw.refund(order_id=order_id, amount=float(amount), method=method)
        except Exception as exc:
            logger.debug("[환불] PaymentGateway 연동 실패 (mock fallback): %s", exc)

        # Mock 응답
        return {
            'pg_transaction_id': f'PG-REFUND-{order_id}',
            'status': 'success',
            'amount': str(amount),
            'method': method,
        }

    def _restore_points(self, user_id: str, amount: Decimal) -> bool:
        """포인트/쿠폰 환원 (src/points/ 연동 시도)."""
        try:
            from ..points.point_manager import PointManager
            mgr = PointManager()
            mgr.add_points(user_id, int(amount), reason='반품 환불')
            logger.info("[환불] 포인트 환원: user=%s, amount=%s", user_id, amount)
            return True
        except Exception as exc:
            logger.debug("[환불] PointManager 연동 실패 (skip): %s", exc)
            return False

    def _send_refund_notification(self, request: AutoReturnRequest, amount: Decimal) -> bool:
        """환불 알림 발송 (NotificationHub 재사용)."""
        try:
            from ..notifications.hub import NotificationHub
            hub = NotificationHub()
            hub.send_order_event(
                order={
                    'order_id': request.order_id,
                    'user_id': request.user_id,
                    'refund_amount': str(amount),
                    'request_id': request.request_id,
                },
                event='payment_refunded',
            )
            return True
        except Exception as exc:
            logger.debug("[환불] NotificationHub 알림 실패 (skip): %s", exc)
            return False
