"""src/ai_pricing/pricing_rules.py — 가격 규칙 ABC + 구현체 (Phase 97)."""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RuleContext:
    """규칙 평가 컨텍스트."""
    sku: str = ''
    current_price: float = 0.0
    cost: float = 0.0                   # 원가
    competitor_min: float = 0.0         # 경쟁사 최저가 (KRW)
    competitor_avg: float = 0.0         # 경쟁사 평균가 (KRW)
    demand_score: float = 1.0           # 수요 지수 (1.0 = 기준)
    stock_qty: int = 100                # 현재 재고
    sales_velocity: float = 0.0        # 일 평균 판매량
    category: str = ''
    season_factor: float = 1.0         # 계절성 가중치
    fx_rate_change: float = 0.0        # 환율 변동율 (%)
    bundle_skus: List[str] = None       # 번들 연관 SKU


@dataclass
class RuleResult:
    """규칙 평가 결과."""
    rule_name: str = ''
    suggested_price: float = 0.0
    confidence: float = 0.5
    reason: str = ''
    applied: bool = True


class PricingRule(abc.ABC):
    """가격 규칙 추상 기반 클래스."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """규칙 이름."""

    @abc.abstractmethod
    def evaluate(self, context: RuleContext) -> Optional[RuleResult]:
        """규칙을 평가하여 가격 제안을 반환한다.

        Returns:
            RuleResult 또는 None (미적용)
        """


class CompetitorMatchRule(PricingRule):
    """경쟁사 최저가 매칭 규칙.

    경쟁사 최저가보다 N원/N% 낮게 설정한다.
    """

    def __init__(self, undercut_pct: float = 0.02, undercut_abs: float = 0.0) -> None:
        """
        Args:
            undercut_pct: 최저가 대비 할인율 (0.02 = 2% 낮게)
            undercut_abs: 절대 할인액 (원), undercut_pct보다 우선
        """
        self._undercut_pct = undercut_pct
        self._undercut_abs = undercut_abs

    @property
    def name(self) -> str:
        return 'competitor_match'

    def evaluate(self, context: RuleContext) -> Optional[RuleResult]:
        if not context.competitor_min or context.competitor_min <= 0:
            return None
        if self._undercut_abs > 0:
            price = context.competitor_min - self._undercut_abs
        else:
            price = context.competitor_min * (1 - self._undercut_pct)
        price = round(price, 2)
        if price <= 0:
            return None
        return RuleResult(
            rule_name=self.name,
            suggested_price=price,
            confidence=0.80,
            reason=f'경쟁사 최저가({context.competitor_min}) 대비 매칭',
        )


class DemandSurgeRule(PricingRule):
    """수요 급증 시 가격 인상 규칙.

    수요 지수가 임계값 이상이면 가격을 인상한다.
    """

    def __init__(
        self,
        surge_threshold: float = 1.5,
        surge_pct: float = 0.10,
        max_surge_pct: float = 0.30,
    ) -> None:
        self._surge_threshold = surge_threshold
        self._surge_pct = surge_pct
        self._max_surge_pct = max_surge_pct

    @property
    def name(self) -> str:
        return 'demand_surge'

    def evaluate(self, context: RuleContext) -> Optional[RuleResult]:
        if context.demand_score < self._surge_threshold:
            return None
        multiplier = min(
            1 + self._surge_pct * (context.demand_score - 1),
            1 + self._max_surge_pct,
        )
        price = round(context.current_price * multiplier, 2)
        return RuleResult(
            rule_name=self.name,
            suggested_price=price,
            confidence=0.70,
            reason=f'수요 급증 감지 (지수={context.demand_score:.2f})',
        )


class SlowMoverRule(PricingRule):
    """판매 부진 상품 자동 할인 규칙.

    재고 회전율이 낮은 상품을 자동으로 할인한다.
    """

    def __init__(
        self,
        slow_threshold_days: float = 30.0,
        discount_pct: float = 0.10,
        max_discount_pct: float = 0.40,
    ) -> None:
        """
        Args:
            slow_threshold_days: 재고 소진 예상 기간(일) 초과 시 할인 적용
            discount_pct: 기본 할인율
            max_discount_pct: 최대 할인율
        """
        self._slow_threshold = slow_threshold_days
        self._discount_pct = discount_pct
        self._max_discount_pct = max_discount_pct

    @property
    def name(self) -> str:
        return 'slow_mover'

    def evaluate(self, context: RuleContext) -> Optional[RuleResult]:
        if context.sales_velocity <= 0 or context.stock_qty <= 0:
            return None
        days_to_clear = context.stock_qty / context.sales_velocity
        if days_to_clear <= self._slow_threshold:
            return None
        # 체류 기간에 비례한 할인율
        extra_ratio = min(
            (days_to_clear - self._slow_threshold) / self._slow_threshold,
            1.0,
        )
        discount = min(self._discount_pct * (1 + extra_ratio), self._max_discount_pct)
        price = round(context.current_price * (1 - discount), 2)
        return RuleResult(
            rule_name=self.name,
            suggested_price=price,
            confidence=0.65,
            reason=f'판매 부진 ({days_to_clear:.0f}일 체류) 할인',
        )


class SeasonalRule(PricingRule):
    """시즌별 가격 조정 규칙.

    성수기는 인상, 비수기는 할인을 적용한다.
    """

    def __init__(
        self,
        peak_threshold: float = 1.15,
        off_threshold: float = 0.90,
        peak_boost: float = 0.08,
        off_discount: float = 0.05,
    ) -> None:
        self._peak_threshold = peak_threshold
        self._off_threshold = off_threshold
        self._peak_boost = peak_boost
        self._off_discount = off_discount

    @property
    def name(self) -> str:
        return 'seasonal'

    def evaluate(self, context: RuleContext) -> Optional[RuleResult]:
        factor = context.season_factor
        if factor >= self._peak_threshold:
            price = round(context.current_price * (1 + self._peak_boost), 2)
            reason = f'성수기 인상 (계절성={factor:.2f})'
        elif factor <= self._off_threshold:
            price = round(context.current_price * (1 - self._off_discount), 2)
            reason = f'비수기 할인 (계절성={factor:.2f})'
        else:
            return None
        return RuleResult(
            rule_name=self.name,
            suggested_price=price,
            confidence=0.75,
            reason=reason,
        )


class BundlePricingRule(PricingRule):
    """번들 상품 연동 가격 규칙 (Phase 44 번들 연동).

    번들 구성 상품 가격이 변경되면 번들 가격도 연동 조정한다.
    """

    def __init__(self, bundle_discount_pct: float = 0.05) -> None:
        self._bundle_discount = bundle_discount_pct

    @property
    def name(self) -> str:
        return 'bundle_pricing'

    def evaluate(self, context: RuleContext) -> Optional[RuleResult]:
        if not context.bundle_skus:
            return None
        # 번들 할인 적용 (구성 상품 수에 비례)
        extra = min(len(context.bundle_skus) * 0.01, 0.10)
        discount = self._bundle_discount + extra
        price = round(context.current_price * (1 - discount), 2)
        return RuleResult(
            rule_name=self.name,
            suggested_price=price,
            confidence=0.70,
            reason=f'번들 할인 적용 ({len(context.bundle_skus)}개 구성)',
        )


class MarginProtectionRule(PricingRule):
    """최소 마진 보호 규칙.

    원가 + 환율 변동을 반영한 최소 마진을 보장한다.
    """

    def __init__(self, min_margin_pct: float = 0.15) -> None:
        """
        Args:
            min_margin_pct: 최소 마진율 (0.15 = 15%)
        """
        self._min_margin = min_margin_pct

    @property
    def name(self) -> str:
        return 'margin_protection'

    def evaluate(self, context: RuleContext) -> Optional[RuleResult]:
        if context.cost <= 0:
            return None
        # 환율 변동 반영 원가
        adjusted_cost = context.cost * (1 + context.fx_rate_change / 100)
        min_price = round(adjusted_cost / (1 - self._min_margin), 2)
        if context.current_price >= min_price:
            return None  # 이미 마진 충족
        return RuleResult(
            rule_name=self.name,
            suggested_price=min_price,
            confidence=1.0,  # 마진 보호는 최우선
            reason=f'최소 마진({self._min_margin * 100:.0f}%) 보호 (원가={adjusted_cost:.2f})',
        )


def get_default_rules() -> List[PricingRule]:
    """기본 가격 규칙 목록을 반환한다."""
    return [
        MarginProtectionRule(),
        CompetitorMatchRule(),
        DemandSurgeRule(),
        SlowMoverRule(),
        SeasonalRule(),
        BundlePricingRule(),
    ]
