"""src/global_commerce/trade/trade_compliance_checker.py — 수출입 규정 체크 (Phase 93)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Set

logger = logging.getLogger(__name__)

# 국제 금지 품목 키워드 (간략 mock)
_PROHIBITED_KEYWORDS: Set[str] = {
    'weapon', 'gun', 'explosive', 'drug', 'narcotic',
    'ivory', 'radioactive', 'counterfeit',
    '총기', '폭발물', '마약', '불법복제', '상아',
}

# 수량 제한 품목 (키워드: 최대 수량)
_QUANTITY_LIMITS: dict = {
    'medicine': 3,
    '의약품': 3,
    'supplement': 6,
    '건강보조식품': 6,
    'cosmetic': 12,
    '화장품': 12,
}

# 수출 제한 국가 (간략 mock — 대북 제재 등)
_EXPORT_RESTRICTED_COUNTRIES: Set[str] = {'KP', 'IR', 'SY', 'CU'}

# 수입 금지 국가 (해당 국가 원산지 수입 금지)
_IMPORT_RESTRICTED_COUNTRIES: Set[str] = {'KP'}


@dataclass
class TradeComplianceResult:
    """수출입 규정 체크 결과."""
    passed: bool
    direction: str
    source_country: str
    destination_country: str
    product_name: str
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'passed': self.passed,
            'direction': self.direction,
            'source_country': self.source_country,
            'destination_country': self.destination_country,
            'product_name': self.product_name,
            'violations': self.violations,
            'warnings': self.warnings,
        }


class TradeComplianceChecker:
    """수출입 규정 체크 — 금지 품목, 수량 제한, 국가 제재."""

    def check_prohibited(self, product_name: str) -> List[str]:
        """금지 품목 여부 체크."""
        name_lower = product_name.lower()
        violations = []
        for keyword in _PROHIBITED_KEYWORDS:
            if keyword in name_lower:
                violations.append(f"금지 품목 감지: '{keyword}' in '{product_name}'")
        return violations

    def check_quantity(self, product_name: str, quantity: int) -> List[str]:
        """수량 제한 체크."""
        name_lower = product_name.lower()
        warnings = []
        for keyword, limit in _QUANTITY_LIMITS.items():
            if keyword in name_lower and quantity > limit:
                warnings.append(
                    f"수량 제한 초과 가능성: '{keyword}' 최대 {limit}개, 요청 {quantity}개"
                )
        return warnings

    def check(self, direction: str, source_country: str,
              destination_country: str, product_name: str,
              quantity: int = 1) -> TradeComplianceResult:
        """수출입 규정 종합 체크.

        Args:
            direction: 무역 방향 ('import'/'export'/'proxy_buy')
            source_country: 출발 국가 코드
            destination_country: 목적지 국가 코드
            product_name: 상품명
            quantity: 수량

        Returns:
            TradeComplianceResult
        """
        source = source_country.upper()
        destination = destination_country.upper()
        violations: List[str] = []
        warnings: List[str] = []

        # 금지 품목 체크
        violations.extend(self.check_prohibited(product_name))

        # 수량 제한 체크
        warnings.extend(self.check_quantity(product_name, quantity))

        # 수출 제한 국가 체크
        if direction in ('export', 'proxy_buy'):
            if destination in _EXPORT_RESTRICTED_COUNTRIES:
                violations.append(f"수출 제한 국가: {destination}")

        # 수입 제한 국가 체크
        if direction == 'import':
            if source in _IMPORT_RESTRICTED_COUNTRIES:
                violations.append(f"수입 금지 국가 원산지: {source}")

        return TradeComplianceResult(
            passed=len(violations) == 0,
            direction=direction,
            source_country=source,
            destination_country=destination,
            product_name=product_name,
            violations=violations,
            warnings=warnings,
        )
