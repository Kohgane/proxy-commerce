"""src/payment_gateway/gateway_manager.py — Phase 45: PG 추상화 ABC + GatewayManager."""
import abc
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PaymentGateway(abc.ABC):
    """결제 게이트웨이 추상 기반 클래스."""

    @abc.abstractmethod
    def initiate_payment(self, amount: float, currency: str, order_id: str, **kwargs) -> dict:
        """결제 요청 생성."""

    @abc.abstractmethod
    def confirm_payment(self, payment_id: str, **kwargs) -> dict:
        """결제 확인."""

    @abc.abstractmethod
    def refund_payment(self, payment_id: str, amount: Optional[float] = None, **kwargs) -> dict:
        """결제 환불."""

    @abc.abstractmethod
    def get_status(self, payment_id: str) -> dict:
        """결제 상태 조회."""


class GatewayManager:
    """PG 선택 (통화/국가 기반), 결제 라우팅."""

    CURRENCY_GATEWAY_MAP: Dict[str, str] = {
        'KRW': 'toss',
        'USD': 'stripe',
        'EUR': 'stripe',
        'JPY': 'paypal',
        'CNY': 'paypal',
    }

    def __init__(self):
        self._gateways: Dict[str, PaymentGateway] = {}

    def register(self, name: str, gateway: PaymentGateway):
        self._gateways[name] = gateway

    def get(self, name: str) -> Optional[PaymentGateway]:
        return self._gateways.get(name)

    def route(self, currency: str, country: Optional[str] = None) -> Optional[PaymentGateway]:
        """통화/국가 기반 최적 PG 선택."""
        gateway_name = self.CURRENCY_GATEWAY_MAP.get(currency.upper(), 'stripe')
        return self._gateways.get(gateway_name)

    def list_gateways(self) -> List[str]:
        return list(self._gateways.keys())
