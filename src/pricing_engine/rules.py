"""가격 산정 규칙 — ABC + 마진/경쟁자/수요 기반 규칙."""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)


class PricingRule(ABC):
    """가격 산정 규칙 추상 기반 클래스."""

    @abstractmethod
    def calculate_price(self) -> Decimal:
        """가격 계산."""


class MarginBasedRule(PricingRule):
    """마진 기반 가격 산정."""

    def __init__(self, cost: Decimal, margin_rate: float, channel_fee_rate: float = 0.0):
        self.cost = Decimal(str(cost))
        self.margin_rate = Decimal(str(margin_rate))
        self.channel_fee_rate = Decimal(str(channel_fee_rate))

    def calculate_price(self) -> Decimal:
        """가격 = 원가 / (1 - 마진율 - 채널수수료율)."""
        divisor = Decimal('1') - self.margin_rate - self.channel_fee_rate
        if divisor <= 0:
            raise ValueError("마진율 + 채널수수료율이 100% 이상입니다.")
        price = (self.cost / divisor).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        logger.debug("마진 기반 가격: 원가=%s, 마진율=%s -> %s", self.cost, self.margin_rate, price)
        return price


class CompetitorBasedRule(PricingRule):
    """경쟁자 가격 기반 산정."""

    def __init__(self, competitor_price: Decimal, adjustment_pct: float = -0.01):
        self.competitor_price = Decimal(str(competitor_price))
        self.adjustment_pct = Decimal(str(adjustment_pct))

    def calculate_price(self) -> Decimal:
        """가격 = 경쟁자 가격 * (1 + 조정률)."""
        price = (self.competitor_price * (Decimal('1') + self.adjustment_pct))
        price = price.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        logger.debug("경쟁자 기반 가격: 경쟁자=%s, 조정=%s -> %s", self.competitor_price, self.adjustment_pct, price)
        return price


class DemandBasedRule(PricingRule):
    """수요 기반 가격 산정."""

    def __init__(self, base_price: Decimal, demand_index: float):
        self.base_price = Decimal(str(base_price))
        self.demand_index = Decimal(str(demand_index))

    def calculate_price(self) -> Decimal:
        """가격 = 기준 가격 * 수요 지수."""
        price = (self.base_price * self.demand_index).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        logger.debug("수요 기반 가격: 기준=%s, 수요지수=%s -> %s", self.base_price, self.demand_index, price)
        return price
