"""자동 가격 산정 엔진."""

import logging
from decimal import Decimal

from .rules import MarginBasedRule, CompetitorBasedRule, DemandBasedRule
from .price_history import PriceHistory
from .alerts import PriceAlerts

logger = logging.getLogger(__name__)


class AutoPricer:
    """자동 가격 산정 실행."""

    def __init__(self):
        self._history = PriceHistory()
        self._alerts = PriceAlerts()
        self._current_prices: dict = {}

    def simulate(self, sku: str, market_data: dict) -> dict:
        """가격 시뮬레이션.

        Args:
            sku: 상품 SKU
            market_data: 시장 데이터 (cost, margin_rate, competitor_price, demand_index)

        Returns:
            시뮬레이션 결과
        """
        results = {}

        cost = Decimal(str(market_data.get('cost', 0)))
        margin_rate = float(market_data.get('margin_rate', 0.3))
        channel_fee = float(market_data.get('channel_fee_rate', 0.05))

        try:
            results['margin_based'] = str(MarginBasedRule(cost, margin_rate, channel_fee).calculate_price())
        except Exception as exc:
            results['margin_based'] = f'오류: {exc}'

        competitor_price = market_data.get('competitor_price')
        if competitor_price:
            adj = float(market_data.get('adjustment_pct', -0.01))
            results['competitor_based'] = str(
                CompetitorBasedRule(Decimal(str(competitor_price)), adj).calculate_price()
            )

        demand_index = market_data.get('demand_index')
        if demand_index and cost > 0:
            results['demand_based'] = str(DemandBasedRule(cost, float(demand_index)).calculate_price())

        logger.info("가격 시뮬레이션: %s -> %s", sku, results)
        return {'sku': sku, 'prices': results, 'market_data': market_data}

    def run(self, skus: list = None, dry_run: bool = False) -> dict:
        """자동 가격 산정 실행.

        Args:
            skus: 대상 SKU 목록 (None이면 전체)
            dry_run: True이면 실제 적용 안 함

        Returns:
            실행 결과
        """
        target_skus = skus or list(self._current_prices.keys())
        results = []

        for sku in target_skus:
            current = self._current_prices.get(sku, Decimal('0'))
            new_price = current

            if not dry_run and new_price > 0:
                self._history.record(sku, new_price)
                if self._alerts.check(sku, current, new_price):
                    self._alerts.send_alert(sku, current, new_price)

            results.append({'sku': sku, 'old_price': str(current), 'new_price': str(new_price)})

        return {
            'dry_run': dry_run,
            'processed': len(results),
            'results': results,
        }
