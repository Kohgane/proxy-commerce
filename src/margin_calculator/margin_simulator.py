"""src/margin_calculator/margin_simulator.py — 마진 시뮬레이터 (Phase 110).

MarginSimulator: 가격/환율/비용 변경 시 마진 영향 시뮬레이션
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .calculator import MarginResult, RealTimeMarginCalculator

logger = logging.getLogger(__name__)

_SIMULATION_TOLERANCE = 0.01   # 손익분기 탐색 수렴 허용 오차 (원)


class MarginSimulator:
    """가격/환율/배송비 변경 마진 영향 시뮬레이션."""

    def __init__(self, calculator: Optional[RealTimeMarginCalculator] = None) -> None:
        self._calc = calculator or RealTimeMarginCalculator()

    # ── 단일 요소 시뮬레이션 ──────────────────────────────────────────────────

    def simulate_price_change(
        self,
        product_id: str,
        new_price: float,
        channel: str = 'internal',
    ) -> Dict[str, Any]:
        """가격 변경 시 마진 변화."""
        before = self._calc.calculate_margin(product_id, channel)
        data = dict(self._calc.get_product(product_id) or {})
        data['selling_price'] = new_price
        after = self._calc.calculate_margin(
            product_id, channel, use_cache=False, product_data=data
        )
        return self._compare(before, after, 'price_change', new_price=new_price)

    def simulate_exchange_rate(
        self,
        product_id: str,
        new_rate: float,
        channel: str = 'internal',
    ) -> Dict[str, Any]:
        """환율 변동 시 마진 변화."""
        before = self._calc.calculate_margin(product_id, channel)
        data = dict(self._calc.get_product(product_id) or {})
        data['exchange_rate'] = new_rate
        after = self._calc.calculate_margin(
            product_id, channel, use_cache=False, product_data=data
        )
        return self._compare(before, after, 'exchange_rate_change', new_rate=new_rate)

    def simulate_cost_change(
        self,
        product_id: str,
        cost_type: str,
        new_value: float,
        channel: str = 'internal',
    ) -> Dict[str, Any]:
        """비용 변경 시 마진 변화.

        cost_type: source_cost, international_shipping, domestic_shipping,
                   customs_duty_rate, payment_fee_rate, packaging_cost, misc_costs 등
        """
        before = self._calc.calculate_margin(product_id, channel)
        data = dict(self._calc.get_product(product_id) or {})
        data[cost_type] = new_value
        after = self._calc.calculate_margin(
            product_id, channel, use_cache=False, product_data=data
        )
        return self._compare(before, after, 'cost_change', cost_type=cost_type, new_value=new_value)

    # ── 손익분기/목표가 계산 ──────────────────────────────────────────────────

    def find_break_even_price(
        self,
        product_id: str,
        channel: str = 'internal',
    ) -> Dict[str, Any]:
        """손익분기 판매가 계산 (이진 탐색)."""
        data = self._calc.get_product(product_id) or {}
        price = self._binary_search_price(product_id, channel, data, target_margin=0.0)
        result = self._calc.calculate_margin(
            product_id, channel, use_cache=False,
            product_data={**data, 'selling_price': price},
        )
        return {
            'product_id': product_id,
            'channel': channel,
            'break_even_price': round(price),
            'margin_rate_at_break_even': result.margin_rate,
            'net_profit_at_break_even': result.net_profit,
        }

    def find_target_margin_price(
        self,
        product_id: str,
        target_margin: float,
        channel: str = 'internal',
    ) -> Dict[str, Any]:
        """목표 마진율 달성 판매가 계산."""
        data = self._calc.get_product(product_id) or {}
        price = self._binary_search_price(product_id, channel, data, target_margin=target_margin)
        result = self._calc.calculate_margin(
            product_id, channel, use_cache=False,
            product_data={**data, 'selling_price': price},
        )
        return {
            'product_id': product_id,
            'channel': channel,
            'target_margin': target_margin,
            'required_price': round(price),
            'margin_rate_achieved': result.margin_rate,
            'net_profit': result.net_profit,
        }

    # ── 복수 시나리오 분석 ────────────────────────────────────────────────────

    def what_if_analysis(
        self,
        product_id: str,
        scenarios: List[Dict[str, Any]],
        channel: str = 'internal',
    ) -> Dict[str, Any]:
        """복수 시나리오 비교 분석.

        scenarios: [{'name': 'S1', 'changes': {'selling_price': 20000, ...}}, ...]
        """
        base_data = dict(self._calc.get_product(product_id) or {})
        baseline = self._calc.calculate_margin(product_id, channel)

        scenario_results = []
        for s in scenarios:
            name = s.get('name', 'unnamed')
            changes = s.get('changes', {})
            data = {**base_data, **changes}
            result = self._calc.calculate_margin(
                product_id, channel, use_cache=False, product_data=data
            )
            scenario_results.append({
                'name': name,
                'changes': changes,
                'margin_rate': result.margin_rate,
                'net_profit': result.net_profit,
                'total_cost': result.total_cost,
                'selling_price': result.selling_price,
                'delta_margin': round(result.margin_rate - baseline.margin_rate, 4),
                'delta_profit': round(result.net_profit - baseline.net_profit, 2),
            })

        return {
            'product_id': product_id,
            'channel': channel,
            'baseline': baseline.to_dict(),
            'scenarios': scenario_results,
        }

    # ── 내부 유틸 ─────────────────────────────────────────────────────────────

    def _compare(
        self,
        before: MarginResult,
        after: MarginResult,
        change_type: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        return {
            'product_id': before.product_id,
            'channel': before.channel,
            'change_type': change_type,
            **extra,
            'before': before.to_dict(),
            'after': after.to_dict(),
            'delta_margin_rate': round(after.margin_rate - before.margin_rate, 4),
            'delta_net_profit': round(after.net_profit - before.net_profit, 2),
            'delta_total_cost': round(after.total_cost - before.total_cost, 2),
        }

    def _binary_search_price(
        self,
        product_id: str,
        channel: str,
        data: Dict[str, Any],
        target_margin: float,
        lo: float = 100.0,
        hi: float = 10_000_000.0,
        iterations: int = 60,
    ) -> float:
        """이진 탐색으로 목표 마진율 달성 판매가 탐색."""
        for _ in range(iterations):
            mid = (lo + hi) / 2.0
            test_data = {**data, 'selling_price': mid}
            result = self._calc.calculate_margin(
                product_id, channel, use_cache=False, product_data=test_data
            )
            if abs(result.margin_rate - target_margin) < 0.001:
                return mid
            if result.margin_rate < target_margin:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0
