"""src/auto_purchase/source_selector.py — 최적 소스 자동 선택 엔진 (Phase 96)."""
from __future__ import annotations

import abc
import logging
from typing import List, Optional

from .purchase_models import SourceOption

logger = logging.getLogger(__name__)


class SelectionStrategy(str):
    CHEAPEST_FIRST = 'cheapest_first'
    FASTEST_DELIVERY = 'fastest_delivery'
    RELIABILITY_FIRST = 'reliability_first'
    BALANCED = 'balanced'


class SourceSelectionStrategy(abc.ABC):
    """소스 선택 전략 추상 기반 클래스."""

    @abc.abstractmethod
    def select(self, options: List[SourceOption]) -> Optional[SourceOption]:
        """최적 소스를 선택한다."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """전략 이름."""


class CheapestFirst(SourceSelectionStrategy):
    """최저가 소스 우선 전략."""

    @property
    def name(self) -> str:
        return SelectionStrategy.CHEAPEST_FIRST

    def select(self, options: List[SourceOption]) -> Optional[SourceOption]:
        available = [o for o in options if o.availability]
        if not available:
            return None
        return min(available, key=lambda o: o.total_cost)


class FastestDelivery(SourceSelectionStrategy):
    """최단 배송 소스 우선 전략."""

    @property
    def name(self) -> str:
        return SelectionStrategy.FASTEST_DELIVERY

    def select(self, options: List[SourceOption]) -> Optional[SourceOption]:
        available = [o for o in options if o.availability]
        if not available:
            return None
        return min(available, key=lambda o: o.estimated_delivery_days)


class ReliabilityFirst(SourceSelectionStrategy):
    """공급자 신뢰도 우선 전략.

    기존 SupplierScoring 연동: seller_rating을 직접 활용.
    """

    @property
    def name(self) -> str:
        return SelectionStrategy.RELIABILITY_FIRST

    def select(self, options: List[SourceOption]) -> Optional[SourceOption]:
        available = [o for o in options if o.availability]
        if not available:
            return None
        return max(available, key=lambda o: o.seller_rating)


class BalancedStrategy(SourceSelectionStrategy):
    """가중 점수 기반 균형 전략.

    가격(40%) + 배송(30%) + 신뢰도(30%) 복합 점수.
    """

    WEIGHT_PRICE = 0.4
    WEIGHT_DELIVERY = 0.3
    WEIGHT_RELIABILITY = 0.3

    @property
    def name(self) -> str:
        return SelectionStrategy.BALANCED

    def _score(self, option: SourceOption, all_options: List[SourceOption]) -> float:
        """복합 점수를 계산한다 (높을수록 좋음)."""
        available = [o for o in all_options if o.availability]
        if not available:
            return 0.0

        prices = [o.total_cost for o in available]
        max_price = max(prices) or 1.0
        min_price = min(prices) or 1.0

        deliveries = [o.estimated_delivery_days for o in available]
        max_delivery = max(deliveries) or 1.0

        # 가격 점수: 최저가에 가까울수록 높음
        if max_price > min_price:
            price_score = 1.0 - (option.total_cost - min_price) / (max_price - min_price)
        else:
            price_score = 1.0

        # 배송 점수: 빠를수록 높음
        delivery_score = 1.0 - (option.estimated_delivery_days / max_delivery) if max_delivery > 0 else 1.0

        # 신뢰도 점수: 0~5 스케일을 0~1로 정규화
        reliability_score = option.seller_rating / 5.0

        return (
            price_score * self.WEIGHT_PRICE
            + delivery_score * self.WEIGHT_DELIVERY
            + reliability_score * self.WEIGHT_RELIABILITY
        )

    def select(self, options: List[SourceOption]) -> Optional[SourceOption]:
        available = [o for o in options if o.availability]
        if not available:
            return None
        return max(available, key=lambda o: self._score(o, available))

    def score_all(self, options: List[SourceOption]) -> List[dict]:
        """모든 옵션의 점수를 반환한다."""
        available = [o for o in options if o.availability]
        return [
            {
                'marketplace': o.marketplace,
                'product_id': o.product_id,
                'score': round(self._score(o, available), 4),
                'price': o.total_cost,
                'delivery_days': o.estimated_delivery_days,
                'seller_rating': o.seller_rating,
            }
            for o in options
        ]


# ---------------------------------------------------------------------------
# SourceSelector — 전략 관리 + 자동 선택
# ---------------------------------------------------------------------------

_STRATEGY_MAP = {
    SelectionStrategy.CHEAPEST_FIRST: CheapestFirst,
    SelectionStrategy.FASTEST_DELIVERY: FastestDelivery,
    SelectionStrategy.RELIABILITY_FIRST: ReliabilityFirst,
    SelectionStrategy.BALANCED: BalancedStrategy,
}


class SourceSelector:
    """최적 소스 자동 선택 엔진."""

    def __init__(self, default_strategy: str = SelectionStrategy.BALANCED) -> None:
        self._default_strategy = default_strategy
        self._strategies: dict[str, SourceSelectionStrategy] = {
            name: cls() for name, cls in _STRATEGY_MAP.items()
        }

    def select(
        self,
        options: List[SourceOption],
        strategy: str = None,
    ) -> Optional[SourceOption]:
        """지정된 전략으로 최적 소스를 선택한다."""
        strategy_name = strategy or self._default_strategy
        strat = self._strategies.get(strategy_name)
        if not strat:
            logger.warning('Unknown strategy: %s, falling back to balanced', strategy_name)
            strat = self._strategies[SelectionStrategy.BALANCED]

        result = strat.select(options)
        if result:
            logger.info(
                'Source selected [%s]: %s/%s (price: %.2f, delivery: %d days)',
                strategy_name, result.marketplace, result.product_id,
                result.total_cost, result.estimated_delivery_days,
            )
        else:
            logger.warning('No available source found for %d options', len(options))
        return result

    def score_all(self, options: List[SourceOption]) -> List[dict]:
        """균형 전략으로 모든 옵션의 점수를 반환한다."""
        strat = self._strategies[SelectionStrategy.BALANCED]
        return strat.score_all(options)  # type: ignore[attr-defined]

    def list_strategies(self) -> List[str]:
        """사용 가능한 전략 목록을 반환한다."""
        return list(self._strategies.keys())
