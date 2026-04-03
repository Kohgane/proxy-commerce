"""src/payment_recovery/payment_recovery_manager.py — 결제 복구 관리자."""
from __future__ import annotations

from .models import FailedPayment


class PaymentRecoveryManager:
    """결제 복구 관리자."""

    def __init__(self) -> None:
        self._failures: dict[str, FailedPayment] = {}

    def track_failure(
        self, payment_id: str, order_id: str, amount: float, error_code: str
    ) -> dict:
        """결제 실패를 추적한다."""
        fp = FailedPayment(
            payment_id=payment_id,
            order_id=order_id,
            amount=amount,
            error_code=error_code,
        )
        self._failures[payment_id] = fp
        return {
            'payment_id': payment_id,
            'order_id': order_id,
            'amount': amount,
            'error_code': error_code,
            'status': fp.status,
        }

    def list_failures(self) -> list:
        """실패한 결제 목록을 반환한다."""
        return [
            {
                'payment_id': fp.payment_id,
                'order_id': fp.order_id,
                'amount': fp.amount,
                'error_code': fp.error_code,
                'attempts': fp.attempts,
                'status': fp.status,
            }
            for fp in self._failures.values()
        ]

    def retry(self, payment_id: str) -> dict:
        """결제를 재시도한다."""
        if payment_id not in self._failures:
            raise KeyError(f'Payment not found: {payment_id}')
        fp = self._failures[payment_id]
        fp.attempts += 1
        success = fp.attempts % 3 == 0
        if success:
            fp.status = 'recovered'
        return {'payment_id': payment_id, 'success': success, 'attempts': fp.attempts}
