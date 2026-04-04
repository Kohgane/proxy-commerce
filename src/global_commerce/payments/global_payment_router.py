"""src/global_commerce/payments/global_payment_router.py — 국가/통화별 PG 라우팅 (Phase 93)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 국가/통화 → 우선 PG 매핑
_COUNTRY_PG_MAP: Dict[str, str] = {
    'KR': 'toss',
    'CN': 'alipay',
    'US': 'stripe',
    'GB': 'stripe',
    'JP': 'stripe',
    'EU': 'stripe',
    'AU': 'stripe',
    'CA': 'stripe',
}

_CURRENCY_PG_MAP: Dict[str, str] = {
    'KRW': 'toss',
    'CNY': 'alipay',
    'USD': 'stripe',
    'EUR': 'stripe',
    'GBP': 'stripe',
    'JPY': 'stripe',
    'AUD': 'stripe',
    'CAD': 'stripe',
}

# PG별 지원 통화
_PG_CURRENCIES: Dict[str, List[str]] = {
    'stripe': ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'HKD', 'SGD', 'SEK', 'NOK', 'DKK'],
    'paypal': ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'HKD', 'SGD'],
    'alipay': ['CNY', 'USD', 'HKD'],
    'toss': ['KRW'],
}


@dataclass
class PaymentRouteResult:
    """PG 라우팅 결과."""
    pg_name: str
    country: str
    currency: str
    supported: bool
    alternative_pgs: List[str] = field(default_factory=list)
    reason: str = ''

    def to_dict(self) -> dict:
        return {
            'pg_name': self.pg_name,
            'country': self.country,
            'currency': self.currency,
            'supported': self.supported,
            'alternative_pgs': self.alternative_pgs,
            'reason': self.reason,
        }


@dataclass
class MockPaymentResult:
    """Mock 결제 결과."""
    payment_id: str
    pg_name: str
    amount: float
    currency: str
    status: str
    order_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            'payment_id': self.payment_id,
            'pg_name': self.pg_name,
            'amount': self.amount,
            'currency': self.currency,
            'status': self.status,
            'order_id': self.order_id,
            'created_at': self.created_at,
        }


class _StripeMock:
    name = 'stripe'

    def pay(self, amount: float, currency: str, order_id: str) -> MockPaymentResult:
        return MockPaymentResult(
            payment_id=f"pi_{uuid.uuid4().hex[:20]}",
            pg_name=self.name,
            amount=amount,
            currency=currency,
            status='succeeded',
            order_id=order_id,
        )


class _PayPalMock:
    name = 'paypal'

    def pay(self, amount: float, currency: str, order_id: str) -> MockPaymentResult:
        return MockPaymentResult(
            payment_id=f"PAYID-{uuid.uuid4().hex[:16].upper()}",
            pg_name=self.name,
            amount=amount,
            currency=currency,
            status='COMPLETED',
            order_id=order_id,
        )


class _AlipayMock:
    name = 'alipay'

    def pay(self, amount: float, currency: str, order_id: str) -> MockPaymentResult:
        return MockPaymentResult(
            payment_id=f"2026{uuid.uuid4().hex[:20]}",
            pg_name=self.name,
            amount=amount,
            currency=currency,
            status='TRADE_SUCCESS',
            order_id=order_id,
        )


class _TossMock:
    name = 'toss'

    def pay(self, amount: float, currency: str, order_id: str) -> MockPaymentResult:
        return MockPaymentResult(
            payment_id=f"tossPayments_{uuid.uuid4().hex[:16]}",
            pg_name=self.name,
            amount=amount,
            currency=currency,
            status='DONE',
            order_id=order_id,
        )


_PG_INSTANCES: Dict[str, object] = {
    'stripe': _StripeMock(),
    'paypal': _PayPalMock(),
    'alipay': _AlipayMock(),
    'toss': _TossMock(),
}


class GlobalPaymentRouter:
    """국가/통화별 최적 PG 라우팅."""

    def route(self, country: str, currency: str) -> PaymentRouteResult:
        """국가/통화 기반 최적 PG 선택.

        Args:
            country: ISO 3166-1 alpha-2 국가 코드
            currency: ISO 4217 통화 코드

        Returns:
            PaymentRouteResult
        """
        country = country.upper()
        currency = currency.upper()

        # 국가 우선 매핑
        pg_name = _COUNTRY_PG_MAP.get(country)
        if pg_name is None:
            # 통화 기반 폴백
            pg_name = _CURRENCY_PG_MAP.get(currency, 'stripe')

        supported = currency in _PG_CURRENCIES.get(pg_name, [])

        # 대안 PG 목록 (현재 PG 제외)
        alternatives = [
            name for name, currencies in _PG_CURRENCIES.items()
            if name != pg_name and currency in currencies
        ]

        reason = f"{country} 국가 → {pg_name} 선택" if country in _COUNTRY_PG_MAP else \
                 f"{currency} 통화 → {pg_name} 선택"

        return PaymentRouteResult(
            pg_name=pg_name,
            country=country,
            currency=currency,
            supported=supported,
            alternative_pgs=alternatives,
            reason=reason,
        )

    def process_payment(self, country: str, currency: str,
                        amount: float, order_id: str) -> MockPaymentResult:
        """국가/통화 기반 결제 처리 (mock).

        Args:
            country: 국가 코드
            currency: 통화 코드
            amount: 결제 금액
            order_id: 주문 ID

        Returns:
            MockPaymentResult
        """
        route = self.route(country, currency)
        pg = _PG_INSTANCES.get(route.pg_name, _PG_INSTANCES['stripe'])
        return pg.pay(amount=amount, currency=currency, order_id=order_id)

    def list_supported_countries(self) -> List[str]:
        return list(_COUNTRY_PG_MAP.keys())

    def list_supported_currencies(self) -> List[str]:
        all_currencies = set()
        for currencies in _PG_CURRENCIES.values():
            all_currencies.update(currencies)
        return sorted(all_currencies)
