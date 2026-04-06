"""src/margin_calculator/cost_breakdown.py — 비용 항목별 상세 분해 (Phase 110).

CostBreakdownService: 상품별 비용 항목 분해 + 비중 계산
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .calculator import RealTimeMarginCalculator

logger = logging.getLogger(__name__)


class CostBreakdownService:
    """비용 항목별 상세 분해."""

    def __init__(self, calculator: Optional[RealTimeMarginCalculator] = None) -> None:
        self._calc = calculator or RealTimeMarginCalculator()

    def get_cost_breakdown(
        self,
        product_id: str,
        channel: str = 'internal',
        product_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """전체 비용 항목 분해.

        Returns:
            {
              'product_id': ...,
              'channel': ...,
              'selling_price': ...,
              'costs': { 항목: 금액, ... },
              'percentages': { 항목: 비중%, ... },   # 파이차트용
              'total_cost': ...,
              'net_profit': ...,
              'margin_rate': ...,
            }
        """
        result = self._calc.calculate_margin(
            product_id, channel, product_data=product_data
        )

        costs: Dict[str, float] = {
            'source_cost_krw': result.source_cost_krw,
            'international_shipping': result.international_shipping,
            'customs_duty': result.customs_duty,
            'vat': result.vat,
            'domestic_shipping': result.domestic_shipping,
            'platform_fee': result.platform_fee,
            'payment_fee': result.payment_fee,
            'exchange_spread': result.exchange_loss,
            'packaging_cost': result.packaging_cost,
            'labeling_cost': result.labeling_cost,
            'return_reserve': result.return_reserve,
            'misc_costs': result.misc_costs,
        }

        # 비중 계산 (판매가 기준)
        selling_price = result.selling_price
        percentages: Dict[str, float] = {}
        if selling_price > 0:
            for k, v in costs.items():
                percentages[k] = round(v / selling_price * 100.0, 2)
        else:
            percentages = {k: 0.0 for k in costs}

        return {
            'product_id': product_id,
            'channel': channel,
            'selling_price': selling_price,
            'source_cost': result.source_cost,
            'currency': result.currency,
            'exchange_rate': result.exchange_rate,
            'costs': costs,
            'percentages': percentages,
            'total_cost': result.total_cost,
            'net_profit': result.net_profit,
            'margin_rate': result.margin_rate,
            'calculated_at': result.calculated_at,
        }
