"""구매대행 마진 정밀 계산기.

기존 src/price.py (calc_landed_cost)를 래핑하여 마켓별 수수료,
배대지비, 배송비, 관세/부가세를 통합 계산한다.
"""

import logging
from decimal import Decimal

from .fee_table import (
    CUSTOMS_THRESHOLDS,
    get_commission_rate,
    get_forwarder_fee,
    get_shipping_cost,
)

logger = logging.getLogger(__name__)


class ProxyMarginCalculator:
    """구매대행 마진 정밀 계산기."""

    def __init__(self, fx_rates: dict | None = None):
        if fx_rates is None:
            try:
                from src.price import _build_fx_rates
                fx_rates = _build_fx_rates()
            except Exception:
                fx_rates = {
                    'USDKRW': Decimal('1350'),
                    'JPYKRW': Decimal('9.0'),
                    'EURKRW': Decimal('1470'),
                    'CNYKRW': Decimal('185'),
                }
        self.fx_rates = {k: Decimal(str(v)) for k, v in fx_rates.items()}

    def _to_krw(self, amount: Decimal, currency: str) -> Decimal:
        if currency == 'KRW':
            return amount
        key = f'{currency}KRW'
        rate = self.fx_rates.get(key)
        if rate is None:
            raise ValueError(f'지원하지 않는 통화: {currency}')
        return amount * rate

    def _customs_duty(self, cost_krw: Decimal, source_country: str) -> Decimal:
        threshold_info = CUSTOMS_THRESHOLDS.get(source_country, CUSTOMS_THRESHOLDS.get('JP', {}))
        threshold_usd = threshold_info.get('threshold_usd', Decimal('150'))
        rate = threshold_info.get('rate', Decimal('0.20'))
        usd_rate = self.fx_rates.get('USDKRW', Decimal('1350'))
        threshold_krw = threshold_usd * usd_rate
        if cost_krw > threshold_krw:
            return cost_krw * rate
        return Decimal('0')

    def calculate(
        self,
        buy_price: float | Decimal,
        currency: str,
        source_country: str = 'US',
        target_market: str = 'coupang',
        category: str = 'default',
        margin_pct: float | Decimal = 25,
        shipping_method: str = 'standard',
        extra_cost_krw: float | Decimal = 0,
    ) -> dict:
        """마진 계산 결과를 반환한다.

        Returns:
            {
                'buy_price': 원본 가격,
                'currency': 통화,
                'cost_krw': KRW 환산 원가,
                'forwarder_fee_krw': 배대지비,
                'shipping_fee_krw': 배송비,
                'extra_cost_krw': 추가비용,
                'subtotal_krw': 소계,
                'customs_duty_krw': 관세/부가세,
                'total_cost_krw': 총원가,
                'commission_pct': 마켓 수수료율,
                'margin_pct': 마진율,
                'sell_price_krw': 최종 판매가,
                'commission_krw': 수수료 금액,
                'net_profit_krw': 순이익,
                'net_margin_pct': 순마진율,
            }
        """
        buy = Decimal(str(buy_price))
        margin = Decimal(str(margin_pct))
        extra = Decimal(str(extra_cost_krw))

        cost_krw = self._to_krw(buy, currency)
        forwarder_krw = get_forwarder_fee(source_country)
        shipping_krw = get_shipping_cost(source_country, shipping_method)

        subtotal = cost_krw + forwarder_krw + shipping_krw + extra
        customs = self._customs_duty(cost_krw, source_country)
        total_cost = subtotal + customs

        commission_pct = get_commission_rate(target_market, category)
        sell_price = total_cost * (Decimal('1') + margin / Decimal('100'))
        sell_price = sell_price / (Decimal('1') - commission_pct / Decimal('100'))
        sell_price = sell_price.quantize(Decimal('1'))

        commission_krw = sell_price * commission_pct / Decimal('100')
        net_profit = sell_price - total_cost - commission_krw
        net_margin = (net_profit / sell_price * Decimal('100')).quantize(Decimal('0.01')) if sell_price else Decimal('0')

        return {
            'buy_price': float(buy),
            'currency': currency,
            'cost_krw': int(cost_krw),
            'forwarder_fee_krw': int(forwarder_krw),
            'shipping_fee_krw': int(shipping_krw),
            'extra_cost_krw': int(extra),
            'subtotal_krw': int(subtotal),
            'customs_duty_krw': int(customs),
            'total_cost_krw': int(total_cost),
            'commission_pct': float(commission_pct),
            'margin_pct': float(margin),
            'sell_price_krw': int(sell_price),
            'commission_krw': int(commission_krw),
            'net_profit_krw': int(net_profit),
            'net_margin_pct': float(net_margin),
        }

    def reverse_calculate(
        self,
        target_sell_price: float | Decimal,
        currency: str,
        source_country: str = 'US',
        target_market: str = 'coupang',
        category: str = 'default',
        shipping_method: str = 'standard',
        extra_cost_krw: float | Decimal = 0,
    ) -> dict:
        """목표 판매가에서 역산하여 가능한 최대 매입가를 반환한다."""
        sell = Decimal(str(target_sell_price))
        extra = Decimal(str(extra_cost_krw))

        commission_pct = get_commission_rate(target_market, category)
        after_commission = sell * (Decimal('1') - commission_pct / Decimal('100'))

        forwarder_krw = get_forwarder_fee(source_country)
        shipping_krw = get_shipping_cost(source_country, shipping_method)

        max_cost_krw = after_commission - forwarder_krw - shipping_krw - extra

        threshold_info = CUSTOMS_THRESHOLDS.get(source_country, CUSTOMS_THRESHOLDS.get('JP', {}))
        rate = threshold_info.get('rate', Decimal('0.20'))
        threshold_usd = threshold_info.get('threshold_usd', Decimal('150'))
        usd_rate = self.fx_rates.get('USDKRW', Decimal('1350'))
        threshold_krw = threshold_usd * usd_rate

        if max_cost_krw > threshold_krw * (Decimal('1') + rate):
            max_cost_krw = max_cost_krw / (Decimal('1') + rate)

        key = f'{currency}KRW'
        fx = self.fx_rates.get(key, Decimal('1'))
        max_buy = max_cost_krw / fx if fx else Decimal('0')

        margin_pct = Decimal('0')
        if max_cost_krw > 0:
            margin_pct = ((after_commission - max_cost_krw - forwarder_krw - shipping_krw - extra) / max_cost_krw * Decimal('100')).quantize(Decimal('0.01'))

        return {
            'target_sell_price_krw': int(sell),
            'max_buy_price': round(float(max_buy), 2),
            'currency': currency,
            'max_cost_krw': int(max_cost_krw),
            'margin_pct': float(margin_pct),
        }

    def compare_markets(
        self,
        buy_price: float | Decimal,
        currency: str,
        source_country: str = 'US',
        margin_pct: float | Decimal = 25,
        markets: list[str] | None = None,
    ) -> list[dict]:
        """여러 마켓에서의 판매가/마진을 비교한다."""
        if markets is None:
            markets = ['coupang', 'smartstore', 'elevenst', 'gmarket', 'auction']
        results = []
        for market in markets:
            try:
                calc = self.calculate(
                    buy_price=buy_price,
                    currency=currency,
                    source_country=source_country,
                    target_market=market,
                    margin_pct=margin_pct,
                )
                calc['market'] = market
                results.append(calc)
            except Exception as exc:
                logger.warning('compare_markets: %s 계산 실패: %s', market, exc)
        results.sort(key=lambda r: r.get('net_profit_krw', 0), reverse=True)
        return results

    def batch_calculate(self, items: list[dict]) -> list[dict]:
        """여러 상품의 마진을 일괄 계산한다.

        items: [{'buy_price': ..., 'currency': ..., ...}, ...]
        """
        results = []
        for item in items:
            try:
                calc = self.calculate(**item)
                results.append(calc)
            except Exception as exc:
                results.append({'error': str(exc), 'input': item})
        return results
