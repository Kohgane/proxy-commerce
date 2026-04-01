"""src/payments/pg_client.py — 결제 게이트웨이 추상 클라이언트."""

from abc import ABC, abstractmethod


class PGClient(ABC):
    """결제 게이트웨이 클라이언트 추상 기반 클래스."""

    @abstractmethod
    def request_payment(self, order_id: str, amount: float, **kwargs) -> dict:
        """결제 요청."""

    @abstractmethod
    def confirm_payment(self, payment_key: str, order_id: str, amount: float) -> dict:
        """결제 승인."""

    @abstractmethod
    def cancel_payment(self, payment_key: str, reason: str) -> dict:
        """결제 취소."""
