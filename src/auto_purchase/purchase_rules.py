"""src/auto_purchase/purchase_rules.py — 자동 구매 규칙 엔진 (Phase 96)."""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

logger = logging.getLogger(__name__)

# 규칙 평가 결과
RULE_PASS = 'pass'
RULE_REJECT = 'reject'
RULE_HOLD = 'hold'


@dataclass
class RuleContext:
    """규칙 평가 컨텍스트."""
    product_id: str = ''
    marketplace: str = ''
    unit_price: float = 0.0
    currency: str = 'USD'
    quantity: int = 1
    selling_price: float = 0.0            # 고객 판매가
    daily_order_count: int = 0
    seller_id: str = ''
    metadata: Dict = field(default_factory=dict)

    @property
    def margin_rate(self) -> float:
        """마진율 계산 (0~1)."""
        if self.selling_price <= 0:
            return 0.0
        cost = self.unit_price * self.quantity
        revenue = self.selling_price * self.quantity
        return (revenue - cost) / revenue

    @property
    def total_cost(self) -> float:
        return self.unit_price * self.quantity


@dataclass
class RuleResult:
    """규칙 평가 결과."""
    rule_name: str = ''
    decision: str = RULE_PASS
    reason: str = ''


class PurchaseRule(abc.ABC):
    """자동 구매 규칙 추상 기반 클래스."""

    @abc.abstractmethod
    def evaluate(self, context: RuleContext) -> RuleResult:
        """규칙을 평가하고 결과를 반환한다."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """규칙 이름."""

    @property
    def description(self) -> str:
        return ''


class MaxPriceRule(PurchaseRule):
    """최대 구매가 제한 규칙.

    마진율 기반으로 최대 구매가를 계산해 초과 시 거부.
    """

    def __init__(self, max_price: float = 500.0, currency: str = 'USD') -> None:
        self._max_price = max_price
        self._currency = currency

    @property
    def name(self) -> str:
        return 'max_price'

    @property
    def description(self) -> str:
        return f'최대 구매가 제한: {self._max_price} {self._currency}'

    def evaluate(self, context: RuleContext) -> RuleResult:
        if context.total_cost > self._max_price:
            return RuleResult(
                rule_name=self.name,
                decision=RULE_REJECT,
                reason=f'구매가 {context.total_cost:.2f}가 한도 {self._max_price:.2f} {self._currency} 초과',
            )
        return RuleResult(rule_name=self.name, decision=RULE_PASS)


class MinMarginRule(PurchaseRule):
    """최소 마진율 보장 규칙.

    마진율이 임계값 미만이면 구매 보류.
    """

    def __init__(self, min_margin_rate: float = 0.15) -> None:
        self._min_margin_rate = min_margin_rate

    @property
    def name(self) -> str:
        return 'min_margin'

    @property
    def description(self) -> str:
        return f'최소 마진율: {self._min_margin_rate:.0%}'

    def evaluate(self, context: RuleContext) -> RuleResult:
        if context.selling_price <= 0:
            return RuleResult(
                rule_name=self.name,
                decision=RULE_HOLD,
                reason='판매가 미설정 — 마진 계산 불가',
            )
        if context.margin_rate < self._min_margin_rate:
            return RuleResult(
                rule_name=self.name,
                decision=RULE_HOLD,
                reason=(
                    f'마진율 {context.margin_rate:.1%}이 최소 기준 {self._min_margin_rate:.1%} 미달'
                ),
            )
        return RuleResult(rule_name=self.name, decision=RULE_PASS)


class StockThresholdRule(PurchaseRule):
    """재고 임계값 기반 자동 재주문 규칙.

    현재 재고가 임계값 이하이면 자동 구매 허용.
    """

    def __init__(self, min_stock: int = 5) -> None:
        self._min_stock = min_stock

    @property
    def name(self) -> str:
        return 'stock_threshold'

    @property
    def description(self) -> str:
        return f'재고 임계값: {self._min_stock}개 이하 시 자동 재주문'

    def evaluate(self, context: RuleContext) -> RuleResult:
        current_stock = context.metadata.get('current_stock', self._min_stock)
        if current_stock <= self._min_stock:
            return RuleResult(
                rule_name=self.name,
                decision=RULE_PASS,
                reason=f'재고 {current_stock}개 ≤ 임계값 {self._min_stock}개 → 재주문 승인',
            )
        return RuleResult(
            rule_name=self.name,
            decision=RULE_HOLD,
            reason=f'재고 {current_stock}개 > 임계값 {self._min_stock}개 → 재주문 불필요',
        )


class BlacklistRule(PurchaseRule):
    """블랙리스트 판매자/상품 필터링 규칙."""

    def __init__(
        self,
        blacklist_sellers: List[str] = None,
        blacklist_products: List[str] = None,
    ) -> None:
        self._sellers = set(blacklist_sellers or [])
        self._products = set(blacklist_products or [])

    @property
    def name(self) -> str:
        return 'blacklist'

    @property
    def description(self) -> str:
        return f'블랙리스트: 판매자 {len(self._sellers)}개, 상품 {len(self._products)}개'

    def add_seller(self, seller_id: str) -> None:
        self._sellers.add(seller_id)

    def add_product(self, product_id: str) -> None:
        self._products.add(product_id)

    def evaluate(self, context: RuleContext) -> RuleResult:
        if context.seller_id and context.seller_id in self._sellers:
            return RuleResult(
                rule_name=self.name,
                decision=RULE_REJECT,
                reason=f'블랙리스트 판매자: {context.seller_id}',
            )
        if context.product_id in self._products:
            return RuleResult(
                rule_name=self.name,
                decision=RULE_REJECT,
                reason=f'블랙리스트 상품: {context.product_id}',
            )
        return RuleResult(rule_name=self.name, decision=RULE_PASS)


class DailyLimitRule(PurchaseRule):
    """일일 구매 한도 규칙."""

    def __init__(self, max_daily_orders: int = 50) -> None:
        self._max_daily_orders = max_daily_orders
        self._today: date = date.today()
        self._count: int = 0

    @property
    def name(self) -> str:
        return 'daily_limit'

    @property
    def description(self) -> str:
        return f'일일 구매 한도: {self._max_daily_orders}건'

    def _reset_if_new_day(self) -> None:
        today = date.today()
        if self._today != today:
            self._today = today
            self._count = 0

    def increment(self) -> None:
        self._reset_if_new_day()
        self._count += 1

    def evaluate(self, context: RuleContext) -> RuleResult:
        self._reset_if_new_day()
        daily_count = context.daily_order_count or self._count
        if daily_count >= self._max_daily_orders:
            return RuleResult(
                rule_name=self.name,
                decision=RULE_HOLD,
                reason=f'일일 한도 {self._max_daily_orders}건 초과 ({daily_count}건)',
            )
        return RuleResult(rule_name=self.name, decision=RULE_PASS)


# ---------------------------------------------------------------------------
# PurchaseRuleEngine
# ---------------------------------------------------------------------------

class PurchaseRuleEngine:
    """자동 구매 규칙 엔진.

    등록된 모든 규칙을 순서대로 평가한다.
    하나라도 reject → 전체 reject.
    reject 없이 hold → hold.
    모두 pass → pass.
    """

    def __init__(self) -> None:
        self._rules: List[PurchaseRule] = []
        self._setup_defaults()

    def _setup_defaults(self) -> None:
        """기본 규칙을 등록한다."""
        self._rules = [
            MaxPriceRule(max_price=2000.0),
            MinMarginRule(min_margin_rate=0.15),
            BlacklistRule(),
            DailyLimitRule(max_daily_orders=100),
        ]

    def add_rule(self, rule: PurchaseRule) -> None:
        """규칙을 추가한다."""
        self._rules.append(rule)
        logger.info('Rule added: %s', rule.name)

    def remove_rule(self, rule_name: str) -> bool:
        """이름으로 규칙을 제거한다."""
        for i, rule in enumerate(self._rules):
            if rule.name == rule_name:
                self._rules.pop(i)
                logger.info('Rule removed: %s', rule_name)
                return True
        return False

    def evaluate(self, context: RuleContext) -> Dict:
        """모든 규칙을 평가한다.

        Returns:
            {
                'decision': 'pass' | 'reject' | 'hold',
                'results': [RuleResult, ...],
                'reject_reasons': [...],
                'hold_reasons': [...],
            }
        """
        results: List[RuleResult] = []
        reject_reasons: List[str] = []
        hold_reasons: List[str] = []

        for rule in self._rules:
            result = rule.evaluate(context)
            results.append(result)
            if result.decision == RULE_REJECT:
                reject_reasons.append(result.reason)
            elif result.decision == RULE_HOLD:
                hold_reasons.append(result.reason)

        if reject_reasons:
            final_decision = RULE_REJECT
        elif hold_reasons:
            final_decision = RULE_HOLD
        else:
            final_decision = RULE_PASS

        return {
            'decision': final_decision,
            'results': results,
            'reject_reasons': reject_reasons,
            'hold_reasons': hold_reasons,
        }

    def get_rule_by_name(self, rule_name: str) -> Optional['PurchaseRule']:
        """이름으로 규칙을 조회한다."""
        for rule in self._rules:
            if rule.name == rule_name:
                return rule
        return None

    def list_rules(self) -> List[Dict]:
        """등록된 규칙 목록을 반환한다."""
        return [
            {'name': r.name, 'description': r.description}
            for r in self._rules
        ]
