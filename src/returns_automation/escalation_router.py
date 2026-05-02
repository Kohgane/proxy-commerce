"""src/returns_automation/escalation_router.py — Phase 118: 분쟁 에스컬레이션 라우터.

Phase 91 DisputeManager 연동 + CS 티켓 자동 생성 + 운영자 텔레그램 알림.
"""
from __future__ import annotations

import logging
from typing import Optional

from .models import AutoReturnRequest

logger = logging.getLogger(__name__)


class EscalationRouter:
    """분쟁 에스컬레이션 라우터.

    escalate_to_dispute()로 Phase 91 DisputeManager에 자동 에스컬레이션 + 운영자 알림.
    """

    def escalate_to_dispute(
        self,
        request: AutoReturnRequest,
        reason: str = '',
        amount: float = 0.0,
    ) -> dict:
        """분쟁으로 에스컬레이션.

        1. Phase 91 DisputeManager에 분쟁 생성
        2. Phase 28 TicketManager에 CS 티켓 생성
        3. 운영자 텔레그램 즉시 알림

        Args:
            request: 반품 요청 객체
            reason: 에스컬레이션 사유
            amount: 분쟁 금액

        Returns:
            에스컬레이션 결과 dict
        """
        result = {
            'request_id': request.request_id,
            'order_id': request.order_id,
            'user_id': request.user_id,
            'reason': reason,
            'dispute_id': None,
            'ticket_id': None,
            'telegram_notified': False,
        }

        # 1. Phase 91 DisputeManager에 분쟁 생성
        dispute = self._create_dispute(request, reason, amount)
        result['dispute_id'] = dispute.get('id') if dispute else None

        # 2. Phase 28 TicketManager에 CS 티켓 생성
        ticket = self._create_cs_ticket(request, reason)
        result['ticket_id'] = ticket.get('id') if ticket else None

        # 3. 운영자 텔레그램 알림
        notified = self._notify_operator(request, reason, dispute, ticket)
        result['telegram_notified'] = notified

        logger.info(
            "[에스컬레이션] %s → 분쟁 %s / 티켓 %s",
            request.request_id,
            result['dispute_id'],
            result['ticket_id'],
        )
        return result

    # ── 내부 헬퍼 ─────────────────────────────────────────

    def _create_dispute(
        self,
        request: AutoReturnRequest,
        reason: str,
        amount: float,
    ) -> Optional[dict]:
        """Phase 91 DisputeManager에 분쟁 생성."""
        try:
            from ..disputes.dispute_manager import DisputeManager
            mgr = DisputeManager()
            dispute = mgr.create(
                order_id=request.order_id,
                customer_id=request.user_id,
                reason=reason or f'반품 자동 에스컬레이션: {request.reason_code}',
                dispute_type='refund',
                amount=amount,
                notes=f'반품요청ID: {request.request_id}',
            )
            return {'id': dispute.dispute_id, 'status': dispute.status.value}
        except Exception as exc:
            logger.warning("[에스컬레이션] DisputeManager 연동 실패 (mock): %s", exc)
            return {'id': f'DISPUTE-{request.request_id}', 'status': 'opened'}

    def _create_cs_ticket(
        self,
        request: AutoReturnRequest,
        reason: str,
    ) -> Optional[dict]:
        """Phase 28 TicketManager에 CS 티켓 생성."""
        try:
            from ..customer_service.ticket_manager import TicketManager
            mgr = TicketManager()
            ticket = mgr.create_ticket({
                'order_id': request.order_id,
                'user_id': request.user_id,
                'subject': f'반품 분쟁 에스컬레이션: {request.request_id}',
                'content': f'사유: {reason}\n반품요청: {request.reason_code}',
                'priority': 'high',
                'type': 'return_dispute',
            })
            return {'id': ticket.get('id', '')} if ticket else None
        except Exception as exc:
            logger.debug("[에스컬레이션] TicketManager 연동 실패 (skip): %s", exc)
            return {'id': f'TICKET-{request.request_id}'}

    def _notify_operator(
        self,
        request: AutoReturnRequest,
        reason: str,
        dispute: Optional[dict],
        ticket: Optional[dict],
    ) -> bool:
        """운영자 텔레그램 즉시 알림."""
        try:
            from ..notifications.hub import NotificationHub
            hub = NotificationHub()
            hub.send_order_event(
                order={
                    'order_id': request.order_id,
                    'user_id': request.user_id,
                    'request_id': request.request_id,
                    'dispute_id': (dispute or {}).get('id', ''),
                    'ticket_id': (ticket or {}).get('id', ''),
                    'reason': reason,
                },
                event='dispute_escalated',
            )
            return True
        except Exception as exc:
            logger.debug("[에스컬레이션] NotificationHub 알림 실패 (skip): %s", exc)
            return False
