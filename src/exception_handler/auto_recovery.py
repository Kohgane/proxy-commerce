"""src/exception_handler/auto_recovery.py — 자동 복구 서비스 (Phase 105)."""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RecoveryAction(ABC):
    """자동 복구 액션 추상 기반 클래스."""

    action_name: str = 'base'

    @abstractmethod
    def execute(self, context: Dict) -> Dict:
        """복구 액션 실행. 결과 딕셔너리 반환."""

    def estimated_cost(self, context: Dict) -> float:  # noqa: ARG002
        return 0.0


class ReorderAction(RecoveryAction):
    """재주문 (다른 셀러/마켓에서)."""

    action_name = 'reorder'

    def execute(self, context: Dict) -> Dict:
        order_id = context.get('order_id', '')
        alternative_seller = context.get('alternative_seller', 'auto-selected')
        logger.info("재주문 실행 (mock): order=%s, seller=%s", order_id, alternative_seller)
        return {
            'action': self.action_name,
            'success': True,
            'new_order_id': f'reorder_{uuid.uuid4().hex[:8]}',
            'seller': alternative_seller,
        }

    def estimated_cost(self, context: Dict) -> float:
        return context.get('unit_price', 0.0) * context.get('quantity', 1)


class RefundAction(RecoveryAction):
    """환불 처리."""

    action_name = 'refund'

    def execute(self, context: Dict) -> Dict:
        order_id = context.get('order_id', '')
        amount = context.get('refund_amount', 0.0)
        logger.info("환불 처리 (mock): order=%s, amount=%s", order_id, amount)
        return {
            'action': self.action_name,
            'success': True,
            'refund_id': f'ref_{uuid.uuid4().hex[:8]}',
            'amount': amount,
        }

    def estimated_cost(self, context: Dict) -> float:
        return context.get('refund_amount', 0.0)


class RerouteAction(RecoveryAction):
    """배송 경로 변경."""

    action_name = 'reroute'

    def execute(self, context: Dict) -> Dict:
        order_id = context.get('order_id', '')
        new_route = context.get('new_route', 'standard')
        logger.info("배송 경로 변경 (mock): order=%s, route=%s", order_id, new_route)
        return {
            'action': self.action_name,
            'success': True,
            'new_route': new_route,
            'eta_days': context.get('eta_days', 5),
        }

    def estimated_cost(self, context: Dict) -> float:
        return context.get('reroute_fee', 5000.0)


class EscalateAction(RecoveryAction):
    """수동 처리 에스컬레이션."""

    action_name = 'escalate'

    def execute(self, context: Dict) -> Dict:
        case_id = context.get('case_id', '')
        reason = context.get('reason', '자동 복구 불가')
        logger.warning("에스컬레이션 (mock): case=%s, reason=%s", case_id, reason)
        return {
            'action': self.action_name,
            'success': True,
            'ticket_id': f'ticket_{uuid.uuid4().hex[:8]}',
            'reason': reason,
        }


class CompensateAction(RecoveryAction):
    """보상 처리 (쿠폰/포인트/할인)."""

    action_name = 'compensate'

    def execute(self, context: Dict) -> Dict:
        order_id = context.get('order_id', '')
        comp_type = context.get('compensation_type', 'coupon')
        amount = context.get('compensation_amount', 0.0)
        logger.info("보상 처리 (mock): order=%s, type=%s, amount=%s", order_id, comp_type, amount)
        return {
            'action': self.action_name,
            'success': True,
            'compensation_type': comp_type,
            'amount': amount,
            'coupon_code': f'COMP_{uuid.uuid4().hex[:6].upper()}' if comp_type == 'coupon' else None,
        }

    def estimated_cost(self, context: Dict) -> float:
        return context.get('compensation_amount', 0.0)


@dataclass
class RecoveryAttempt:
    attempt_id: str
    case_id: str
    action_name: str
    context: Dict
    result: Dict
    success: bool
    cost: float
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return {
            'attempt_id': self.attempt_id,
            'case_id': self.case_id,
            'action_name': self.action_name,
            'context': self.context,
            'result': self.result,
            'success': self.success,
            'cost': self.cost,
            'executed_at': self.executed_at,
        }


class AutoRecoveryService:
    """예외별 자동 복구 전략 실행."""

    def __init__(self) -> None:
        self._attempts: Dict[str, RecoveryAttempt] = {}
        self._actions: Dict[str, RecoveryAction] = {
            'reorder': ReorderAction(),
            'refund': RefundAction(),
            'reroute': RerouteAction(),
            'escalate': EscalateAction(),
            'compensate': CompensateAction(),
        }

    def execute(self, action_name: str, case_id: str, context: Optional[Dict] = None) -> RecoveryAttempt:
        ctx = context or {}
        action = self._actions.get(action_name)
        if action is None:
            raise ValueError(f'알 수 없는 복구 액션: {action_name}')

        cost = action.estimated_cost(ctx)
        try:
            result = action.execute(ctx)
            success = result.get('success', False)
        except Exception as exc:
            result = {'action': action_name, 'success': False, 'error': str(exc)}
            success = False

        attempt_id = f'ra_{uuid.uuid4().hex[:10]}'
        attempt = RecoveryAttempt(
            attempt_id=attempt_id,
            case_id=case_id,
            action_name=action_name,
            context=ctx,
            result=result,
            success=success,
            cost=cost,
        )
        self._attempts[attempt_id] = attempt
        logger.info("복구 시도: %s (case=%s, action=%s, success=%s)", attempt_id, case_id, action_name, success)
        return attempt

    def get_attempt(self, attempt_id: str) -> Optional[RecoveryAttempt]:
        return self._attempts.get(attempt_id)

    def list_attempts(self, case_id: Optional[str] = None) -> List[RecoveryAttempt]:
        attempts = list(self._attempts.values())
        if case_id:
            attempts = [a for a in attempts if a.case_id == case_id]
        return attempts

    def get_stats(self) -> Dict:
        attempts = list(self._attempts.values())
        total = len(attempts)
        succeeded = sum(1 for a in attempts if a.success)
        total_cost = sum(a.cost for a in attempts)
        by_action: Dict[str, int] = {}
        for a in attempts:
            by_action[a.action_name] = by_action.get(a.action_name, 0) + 1
        return {
            'total_attempts': total,
            'succeeded': succeeded,
            'success_rate': succeeded / total if total else 0.0,
            'total_cost': total_cost,
            'by_action': by_action,
        }
