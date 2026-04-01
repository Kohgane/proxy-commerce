"""src/payments/toss_client.py — Toss Payments PG 클라이언트."""

import base64
import logging
import os

import requests

from .pg_client import PGClient

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.tosspayments.com/v1"


class TossPaymentsClient(PGClient):
    """Toss Payments API 클라이언트."""

    def __init__(self) -> None:
        self._secret_key = os.getenv("TOSS_PAYMENTS_SECRET_KEY", "")
        if not self._secret_key:
            logger.warning("TOSS_PAYMENTS_SECRET_KEY 환경변수가 설정되지 않았습니다.")

    def _auth_header(self) -> dict:
        token = base64.b64encode(f"{self._secret_key}:".encode()).decode()
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    def request_payment(self, order_id: str, amount: float, **kwargs) -> dict:
        """결제 요청 — checkout URL과 payment_key를 반환한다."""
        method = kwargs.get("method", "카드")
        order_name = kwargs.get("order_name", "주문")
        payment_key = f"toss_{order_id}_{int(amount)}"
        checkout_url = f"{_BASE_URL}/payments/{payment_key}/checkout"
        return {
            "payment_key": payment_key,
            "checkout_url": checkout_url,
            "order_id": order_id,
            "amount": amount,
            "method": method,
            "order_name": order_name,
        }

    def confirm_payment(self, payment_key: str, order_id: str, amount: float) -> dict:
        """결제 승인 — POST /payments/confirm."""
        url = f"{_BASE_URL}/payments/confirm"
        payload = {"paymentKey": payment_key, "orderId": order_id, "amount": amount}
        resp = requests.post(url, json=payload, headers=self._auth_header(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def cancel_payment(self, payment_key: str, reason: str) -> dict:
        """결제 취소 — POST /payments/{payment_key}/cancel."""
        url = f"{_BASE_URL}/payments/{payment_key}/cancel"
        payload = {"cancelReason": reason}
        resp = requests.post(url, json=payload, headers=self._auth_header(), timeout=10)
        resp.raise_for_status()
        return resp.json()
