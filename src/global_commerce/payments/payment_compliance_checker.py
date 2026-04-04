"""src/global_commerce/payments/payment_compliance_checker.py — 해외 결제 규정 체크 (Phase 93)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger(__name__)

# 국가별 단건 거래 한도 (USD)
_SINGLE_TX_LIMIT_USD: Dict[str, float] = {
    'KR': 50000.0,   # 외국환거래법 기준
    'CN': 50000.0,
    'US': 10000.0,   # FinCEN 보고 기준
    'JP': 10000.0,
    'DEFAULT': 10000.0,
}

# KYC 필요 기준 (USD)
_KYC_THRESHOLD_USD: Dict[str, float] = {
    'KR': 3000.0,
    'CN': 2000.0,
    'US': 3000.0,
    'DEFAULT': 3000.0,
}


@dataclass
class ComplianceResult:
    """결제 규정 체크 결과."""
    passed: bool
    country: str
    currency: str
    amount_usd: float
    kyc_required: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'passed': self.passed,
            'country': self.country,
            'currency': self.currency,
            'amount_usd': self.amount_usd,
            'kyc_required': self.kyc_required,
            'violations': self.violations,
            'warnings': self.warnings,
        }


# 환율 (USD 기준, mock)
_TO_USD: Dict[str, float] = {
    'USD': 1.0,
    'KRW': 1 / 1350.0,
    'EUR': 1.08,
    'GBP': 1.26,
    'JPY': 1 / 150.0,
    'CNY': 1 / 7.1,
}


class PaymentComplianceChecker:
    """해외 결제 규정 체크 — 거래 한도, KYC 필요 여부."""

    def _to_usd(self, amount: float, currency: str) -> float:
        rate = _TO_USD.get(currency.upper(), 1 / 1350.0)
        return round(amount * rate, 4)

    def check(self, amount: float, currency: str, country: str) -> ComplianceResult:
        """결제 규정 체크.

        Args:
            amount: 결제 금액
            currency: 결제 통화
            country: 결제 국가 코드

        Returns:
            ComplianceResult
        """
        country = country.upper()
        currency = currency.upper()
        amount_usd = self._to_usd(amount, currency)

        violations: List[str] = []
        warnings: List[str] = []

        # 거래 한도 체크
        limit_usd = _SINGLE_TX_LIMIT_USD.get(country, _SINGLE_TX_LIMIT_USD['DEFAULT'])
        if amount_usd > limit_usd:
            violations.append(
                f"거래 한도 초과: ${amount_usd:.2f} > ${limit_usd:.2f} ({country})"
            )

        # KYC 필요 여부
        kyc_threshold = _KYC_THRESHOLD_USD.get(country, _KYC_THRESHOLD_USD['DEFAULT'])
        kyc_required = amount_usd >= kyc_threshold
        if kyc_required:
            warnings.append(
                f"KYC 인증 필요: ${amount_usd:.2f} >= ${kyc_threshold:.2f} ({country})"
            )

        # 고액 경고
        if amount_usd >= 5000:
            warnings.append(f"고액 거래 검토 필요: ${amount_usd:.2f}")

        passed = len(violations) == 0
        return ComplianceResult(
            passed=passed,
            country=country,
            currency=currency,
            amount_usd=amount_usd,
            kyc_required=kyc_required,
            violations=violations,
            warnings=warnings,
        )

    def get_limit(self, country: str, currency: str = 'USD') -> float:
        """국가별 거래 한도 반환 (USD)."""
        return _SINGLE_TX_LIMIT_USD.get(country.upper(), _SINGLE_TX_LIMIT_USD['DEFAULT'])

    def kyc_threshold(self, country: str) -> float:
        """국가별 KYC 필요 기준 반환 (USD)."""
        return _KYC_THRESHOLD_USD.get(country.upper(), _KYC_THRESHOLD_USD['DEFAULT'])
