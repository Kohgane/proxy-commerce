"""src/vendor_marketplace/commission.py — 수수료 계산 시스템 (Phase 98)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .vendor_models import VendorTier, TIER_COMMISSION_RATES

# 카테고리별 수수료율 오버라이드 (%)
_CATEGORY_RATES: Dict[str, float] = {
    'electronics': 8.0,
    'fashion': 12.0,
    'beauty': 11.0,
    'food': 9.0,
    'sports': 10.0,
    'toys': 11.0,
    'home': 10.0,
    'book': 7.0,
    'auto': 9.0,
    'pet': 10.0,
    'health': 10.0,
    'baby': 11.0,
    'office': 9.0,
    'other': 12.0,
}


@dataclass
class CommissionRule:
    """수수료 규칙 데이터 모델."""
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    vendor_tier: str = ''                  # VendorTier.value
    category: str = ''                     # 카테고리 (빈 문자열 = 전체)
    rate: float = 0.0                      # 수수료율 (%)
    min_amount: float = 0.0               # 최소 적용 금액 (원)
    max_amount: float = float('inf')       # 최대 적용 금액 (원)
    is_active: bool = True
    promotion_rate: Optional[float] = None  # 프로모션 수수료율 (%)
    promotion_until: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def effective_rate(self) -> float:
        """현재 유효 수수료율 (프로모션 기간이면 프로모션율 반환)."""
        now = datetime.now(timezone.utc)
        if (
            self.promotion_rate is not None
            and self.promotion_until is not None
            and now <= self.promotion_until
        ):
            return self.promotion_rate
        return self.rate

    def to_dict(self) -> dict:
        return {
            'rule_id': self.rule_id,
            'vendor_tier': self.vendor_tier,
            'category': self.category,
            'rate': self.rate,
            'effective_rate': self.effective_rate,
            'min_amount': self.min_amount,
            'max_amount': self.max_amount if self.max_amount != float('inf') else None,
            'is_active': self.is_active,
            'promotion_rate': self.promotion_rate,
            'promotion_until': self.promotion_until.isoformat() if self.promotion_until else None,
            'created_at': self.created_at.isoformat(),
        }


class CommissionCalculator:
    """수수료 계산기."""

    def __init__(self) -> None:
        self._rules: Dict[str, CommissionRule] = {}

    # ── 규칙 관리 ─────────────────────────────────────────────────────────

    def add_rule(self, rule: CommissionRule) -> CommissionRule:
        self._rules[rule.rule_id] = rule
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def list_rules(self, active_only: bool = True) -> List[CommissionRule]:
        rules = list(self._rules.values())
        if active_only:
            rules = [r for r in rules if r.is_active]
        return rules

    # ── 수수료 계산 ───────────────────────────────────────────────────────

    def calculate(
        self,
        amount: float,
        vendor_tier: str,
        category: str = '',
    ) -> dict:
        """수수료 계산.

        우선순위:
        1. 해당 tier + category 규칙 (active)
        2. 해당 tier 규칙 (category 무관)
        3. 카테고리 기본 수수료율
        4. 티어 기본 수수료율
        """
        rate = self._resolve_rate(amount, vendor_tier, category)
        commission = round(amount * rate / 100, 2)
        net = round(amount - commission, 2)
        return {
            'amount': amount,
            'vendor_tier': vendor_tier,
            'category': category,
            'rate': rate,
            'commission': commission,
            'net_amount': net,
        }

    def _resolve_rate(self, amount: float, vendor_tier: str, category: str) -> float:
        """적용할 수수료율 결정."""
        active_rules = [r for r in self._rules.values() if r.is_active]

        # 1. tier + category 일치 규칙
        for rule in active_rules:
            if (
                rule.vendor_tier == vendor_tier
                and rule.category == category
                and rule.min_amount <= amount <= rule.max_amount
            ):
                return rule.effective_rate

        # 2. tier 규칙 (category 무관)
        for rule in active_rules:
            if (
                rule.vendor_tier == vendor_tier
                and rule.category == ''
                and rule.min_amount <= amount <= rule.max_amount
            ):
                return rule.effective_rate

        # 3. 카테고리 기본율
        if category in _CATEGORY_RATES:
            return _CATEGORY_RATES[category]

        # 4. 티어 기본율
        return TIER_COMMISSION_RATES.get(vendor_tier, 15.0)

    def bulk_calculate(self, orders: List[dict]) -> List[dict]:
        """다수 주문에 대한 수수료 일괄 계산."""
        results = []
        for order in orders:
            result = self.calculate(
                amount=float(order.get('amount', 0)),
                vendor_tier=order.get('vendor_tier', 'basic'),
                category=order.get('category', ''),
            )
            result['order_id'] = order.get('order_id', '')
            results.append(result)
        return results
