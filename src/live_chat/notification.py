"""src/live_chat/notification.py — 채팅 알림 서비스 (Phase 107)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ChatNotificationService:
    """채팅 관련 알림 발송 (mock)."""

    def __init__(self):
        self._notifications: List[dict] = []

    # ── 알림 발송 메서드 ──────────────────────────────────────────────────────

    def notify_wait_time(self, customer_id: str, estimated_seconds: int) -> dict:
        """대기 예상 시간 안내."""
        minutes = max(1, estimated_seconds // 60)
        note = self._send(
            recipient_id=customer_id,
            recipient_type='customer',
            event='wait_time',
            message=f'현재 대기 중입니다. 예상 대기 시간은 약 {minutes}분입니다.',
            data={'estimated_seconds': estimated_seconds},
        )
        return note

    def notify_agent_assigned(self, customer_id: str, agent_name: str, session_id: str) -> dict:
        """상담원 배정 알림 (고객)."""
        return self._send(
            recipient_id=customer_id,
            recipient_type='customer',
            event='agent_assigned',
            message=f'{agent_name} 상담원이 배정되었습니다.',
            data={'agent_name': agent_name, 'session_id': session_id},
        )

    def notify_new_session(self, agent_id: str, session_id: str, customer_id: str) -> dict:
        """새 채팅 배정 알림 (상담원)."""
        return self._send(
            recipient_id=agent_id,
            recipient_type='agent',
            event='new_session',
            message=f'새 채팅이 배정되었습니다. 고객: {customer_id}',
            data={'session_id': session_id, 'customer_id': customer_id},
        )

    def notify_no_response(self, customer_id: str, session_id: str, minutes: int = 5) -> dict:
        """고객 미응답 리마인더."""
        return self._send(
            recipient_id=customer_id,
            recipient_type='customer',
            event='no_response_reminder',
            message=f'{minutes}분 동안 응답이 없습니다. 채팅을 계속하시겠습니까?',
            data={'session_id': session_id, 'minutes': minutes},
        )

    def request_rating(self, customer_id: str, session_id: str) -> dict:
        """상담 종료 후 만족도 조사 요청."""
        return self._send(
            recipient_id=customer_id,
            recipient_type='customer',
            event='rating_request',
            message='상담이 종료되었습니다. 만족도를 평가해주세요 (1-5점).',
            data={'session_id': session_id},
        )

    def notify_off_hours(self, customer_id: str, session_id: str) -> dict:
        """영업 시간 외 알림."""
        return self._send(
            recipient_id=customer_id,
            recipient_type='customer',
            event='off_hours',
            message='현재 영업 시간이 아닙니다. 문의 내용을 남겨주시면 영업 시간 후 처리해드리겠습니다.',
            data={'session_id': session_id},
        )

    # ── 이력 조회 ─────────────────────────────────────────────────────────────

    def get_notifications(
        self, recipient_id: Optional[str] = None, event: Optional[str] = None
    ) -> List[dict]:
        notes = list(self._notifications)
        if recipient_id:
            notes = [n for n in notes if n['recipient_id'] == recipient_id]
        if event:
            notes = [n for n in notes if n['event'] == event]
        return notes

    def get_stats(self) -> dict:
        total = len(self._notifications)
        by_event: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for n in self._notifications:
            evt = n.get('event', 'unknown')
            rtype = n.get('recipient_type', 'unknown')
            by_event[evt] = by_event.get(evt, 0) + 1
            by_type[rtype] = by_type.get(rtype, 0) + 1
        return {
            'total_sent': total,
            'by_event': by_event,
            'by_recipient_type': by_type,
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _send(
        self,
        recipient_id: str,
        recipient_type: str,
        event: str,
        message: str,
        data: Optional[dict] = None,
    ) -> dict:
        note = {
            'notification_id': f"notif-{len(self._notifications) + 1:04d}",
            'recipient_id': recipient_id,
            'recipient_type': recipient_type,
            'event': event,
            'message': message,
            'data': data or {},
            'sent_at': datetime.now(tz=timezone.utc).isoformat(),
        }
        self._notifications.append(note)
        logger.debug("채팅 알림 발송: %s → %s (%s)", event, recipient_id, recipient_type)
        return note
