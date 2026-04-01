"""src/payments/settlement.py — 정산 계산기."""

import logging

from .fee_calculator import FeeCalculator
from .models import Settlement

logger = logging.getLogger(__name__)


class SettlementCalculator:
    """주문별/기간별 정산을 계산한다."""

    def __init__(self) -> None:
        self._fee_calc = FeeCalculator()

    def calculate(self, order: dict) -> Settlement:
        """단건 주문 정산을 계산하고 Settlement 객체를 반환한다.

        order keys: order_id, sale_price, cost_price, platform, shipping_fee, fx_diff(optional)
        """
        platform_fee = self._fee_calc.calculate_fee(order['platform'], order['sale_price'])
        settlement = Settlement(
            order_id=order['order_id'],
            sale_price=order['sale_price'],
            cost_price=order['cost_price'],
            platform_fee=platform_fee,
            shipping_fee=order.get('shipping_fee', 0.0),
            fx_diff=order.get('fx_diff', 0.0),
        )
        settlement.calculate()
        return settlement

    def calculate_bulk(self, orders: list) -> list:
        """복수 주문 정산을 계산한다."""
        return [self.calculate(o) for o in orders]

    def summarize(self, settlements: list) -> dict:
        """정산 목록의 요약 통계를 반환한다."""
        return {
            'total_revenue': sum(s.sale_price for s in settlements),
            'total_cost': sum(s.cost_price for s in settlements),
            'total_fees': sum(s.platform_fee for s in settlements),
            'total_shipping': sum(s.shipping_fee for s in settlements),
            'total_net_profit': sum(s.net_profit for s in settlements),
            'count': len(settlements),
        }
