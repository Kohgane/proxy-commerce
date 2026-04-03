"""src/payment_recovery/recovery_action.py — 복구 액션."""
from __future__ import annotations


class RecoveryAction:
    """복구 액션 실행기."""

    def execute(self, action_type: str, payment_id: str, **kwargs) -> dict:
        """복구 액션을 실행한다."""
        if action_type == 'retry':
            return {'action': 'retry', 'payment_id': payment_id, 'status': 'scheduled'}
        if action_type == 'notify':
            return {'action': 'notify', 'payment_id': payment_id, 'status': 'sent'}
        if action_type == 'suggest_alternative':
            return {
                'action': 'suggest_alternative',
                'payment_id': payment_id,
                'alternatives': ['virtual_account', 'bank_transfer', 'kakaopay'],
            }
        if action_type == 'cancel':
            return {'action': 'cancel', 'payment_id': payment_id, 'status': 'cancelled'}
        return {'action': action_type, 'payment_id': payment_id, 'status': 'unknown'}
