"""src/global_commerce/shipping/shipping_insurance.py — 국제 배송 보험 (Phase 93)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict

logger = logging.getLogger(__name__)

# 보험료율 (상품 가치 대비)
_INSURANCE_RATE = 0.02   # 2%
_MIN_PREMIUM_KRW = 3000  # 최소 보험료 3,000원
_COVERAGE_RATIO = 1.0    # 전액 보상

# 목적지별 위험 프리미엄
_RISK_PREMIUM: Dict[str, float] = {
    'HIGH': 0.005,     # 고위험 지역 추가 0.5%
    'MEDIUM': 0.002,   # 중위험 추가 0.2%
    'LOW': 0.0,        # 저위험 추가 없음
}

_COUNTRY_RISK: Dict[str, str] = {
    'US': 'LOW',
    'JP': 'LOW',
    'KR': 'LOW',
    'CN': 'MEDIUM',
    'GB': 'LOW',
    'AU': 'LOW',
    'DEFAULT': 'MEDIUM',
}


@dataclass
class InsuranceQuote:
    """배송 보험 견적."""
    declared_value_krw: float
    destination_country: str
    risk_level: str
    base_premium_krw: float
    risk_premium_krw: float
    total_premium_krw: float
    coverage_krw: float

    def to_dict(self) -> dict:
        return {
            'declared_value_krw': self.declared_value_krw,
            'destination_country': self.destination_country,
            'risk_level': self.risk_level,
            'base_premium_krw': self.base_premium_krw,
            'risk_premium_krw': self.risk_premium_krw,
            'total_premium_krw': self.total_premium_krw,
            'coverage_krw': self.coverage_krw,
        }


class ShippingInsurance:
    """국제 배송 보험 계산."""

    def calculate(self, declared_value_krw: float,
                  destination_country: str) -> InsuranceQuote:
        """배송 보험료 계산.

        Args:
            declared_value_krw: 신고 상품 가치 (KRW)
            destination_country: 목적지 국가 코드

        Returns:
            InsuranceQuote
        """
        destination = destination_country.upper()
        risk_level = _COUNTRY_RISK.get(destination, _COUNTRY_RISK['DEFAULT'])
        risk_rate = _RISK_PREMIUM.get(risk_level, 0.0)

        base_premium = max(_MIN_PREMIUM_KRW,
                           round(declared_value_krw * _INSURANCE_RATE, 0))
        risk_premium = round(declared_value_krw * risk_rate, 0)
        total_premium = base_premium + risk_premium
        coverage = declared_value_krw * _COVERAGE_RATIO

        return InsuranceQuote(
            declared_value_krw=declared_value_krw,
            destination_country=destination,
            risk_level=risk_level,
            base_premium_krw=base_premium,
            risk_premium_krw=risk_premium,
            total_premium_krw=total_premium,
            coverage_krw=coverage,
        )

    def risk_level(self, destination_country: str) -> str:
        """목적지 위험 등급 반환."""
        return _COUNTRY_RISK.get(destination_country.upper(), _COUNTRY_RISK['DEFAULT'])
