"""src/payment_gateway/stripe.py — Phase 45: Stripe 어댑터 (mock)."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from .gateway_manager import PaymentGateway

logger = logging.getLogger(__name__)


class StripeGateway(PaymentGateway):
    """Stripe mock 구현."""

    def __init__(self, api_key: str = 'mock_stripe_key'):
        self._api_key = api_key
        self._payments = {}

    def initiate_payment(self, amount: float, currency: str = 'USD',
                         order_id: str = '', **kwargs) -> dict:
        payment_id = f"pi_{uuid.uuid4().hex[:24]}"
        payment = {
            'payment_id': payment_id,
            'gateway': 'stripe',
            'amount': amount,
            'currency': currency,
            'order_id': order_id,
            'status': 'requires_payment_method',
            'client_secret': f"{payment_id}_secret_{uuid.uuid4().hex[:8]}",
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._payments[payment_id] = payment
        logger.info("[Stripe mock] PaymentIntent 생성: %s", payment_id)
        return payment

    def confirm_payment(self, payment_id: str, **kwargs) -> dict:
        payment = self._payments.get(payment_id)
        if payment is None:
            raise KeyError(f"결제 없음: {payment_id}")
        payment['status'] = 'succeeded'
        payment['confirmed_at'] = datetime.now(timezone.utc).isoformat()
        return payment

    def refund_payment(self, payment_id: str, amount: Optional[float] = None, **kwargs) -> dict:
        payment = self._payments.get(payment_id)
        if payment is None:
            raise KeyError(f"결제 없음: {payment_id}")
        refund_id = f"re_{uuid.uuid4().hex[:24]}"
        refund_amount = amount if amount is not None else payment['amount']
        payment['status'] = 'refunded'
        payment['refund_id'] = refund_id
        payment['refund_amount'] = refund_amount
        return payment

    def get_status(self, payment_id: str) -> dict:
        payment = self._payments.get(payment_id)
        if payment is None:
            return {'payment_id': payment_id, 'status': 'not_found'}
        return {'payment_id': payment_id, 'status': payment['status']}
