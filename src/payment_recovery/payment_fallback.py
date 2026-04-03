"""src/payment_recovery/payment_fallback.py — 결제 대안."""
from __future__ import annotations


class PaymentFallback:
    """결제 대안 관리자."""

    def __init__(self) -> None:
        self._alternatives: dict[str, list] = {
            'CARD_DECLINED': ['virtual_account', 'bank_transfer', 'kakaopay'],
            'INSUFFICIENT_FUNDS': ['installment', 'virtual_account'],
            'EXPIRED_CARD': ['new_card', 'kakaopay', 'naverpay'],
            'DEFAULT': ['virtual_account', 'bank_transfer'],
        }

    def suggest_alternatives(self, error_code: str) -> list:
        """대안 결제 수단을 제안한다."""
        return self._alternatives.get(error_code, self._alternatives['DEFAULT'])

    def try_alternative(self, payment_id: str, method: str) -> dict:
        """대안 결제를 시도한다."""
        return {'payment_id': payment_id, 'method': method, 'status': 'attempted'}
