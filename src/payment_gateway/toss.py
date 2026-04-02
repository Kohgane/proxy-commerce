"""src/payment_gateway/toss.py — Phase 45: 토스페이먼츠 어댑터 (mock)."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from .gateway_manager import PaymentGateway

logger = logging.getLogger(__name__)


class TossPaymentsGateway(PaymentGateway):
    """토스페이먼츠 mock 구현."""

    def __init__(self, client_key: str = 'mock_client_key',
                 secret_key: str = 'mock_secret_key'):
        self._client_key = client_key
        self._secret_key = secret_key
        self._payments = {}

    def initiate_payment(self, amount: float, currency: str = 'KRW',
                         order_id: str = '', **kwargs) -> dict:
        payment_id = f"toss_{uuid.uuid4().hex[:12]}"
        payment = {
            'payment_id': payment_id,
            'gateway': 'toss',
            'amount': amount,
            'currency': currency,
            'order_id': order_id,
            'status': 'initiated',
            'checkout_url': f"https://mock.tosspayments.com/checkout/{payment_id}",
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._payments[payment_id] = payment
        logger.info("[Toss mock] 결제 생성: %s", payment_id)
        return payment

    def confirm_payment(self, payment_id: str, **kwargs) -> dict:
        payment = self._payments.get(payment_id)
        if payment is None:
            raise KeyError(f"결제 없음: {payment_id}")
        payment['status'] = 'confirmed'
        payment['confirmed_at'] = datetime.now(timezone.utc).isoformat()
        return payment

    def refund_payment(self, payment_id: str, amount: Optional[float] = None, **kwargs) -> dict:
        payment = self._payments.get(payment_id)
        if payment is None:
            raise KeyError(f"결제 없음: {payment_id}")
        refund_amount = amount if amount is not None else payment['amount']
        payment['status'] = 'refunded'
        payment['refund_amount'] = refund_amount
        payment['refunded_at'] = datetime.now(timezone.utc).isoformat()
        return payment

    def get_status(self, payment_id: str) -> dict:
        payment = self._payments.get(payment_id)
        if payment is None:
            return {'payment_id': payment_id, 'status': 'not_found'}
        return {'payment_id': payment_id, 'status': payment['status']}
