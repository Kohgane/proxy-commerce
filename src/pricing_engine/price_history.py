"""가격 이력 관리."""

import logging
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


class PriceHistory:
    """SKU별 가격 이력 저장 및 조회."""

    def __init__(self):
        self._history: dict = {}

    def record(self, sku: str, price: Decimal, channel: str = 'internal') -> dict:
        """가격 이력 기록.

        Args:
            sku: 상품 SKU
            price: 가격
            channel: 채널명

        Returns:
            기록된 이력 항목
        """
        if sku not in self._history:
            self._history[sku] = []
        entry = {
            'sku': sku,
            'price': str(price),
            'channel': channel,
            'recorded_at': datetime.now().isoformat(),
        }
        self._history[sku].append(entry)
        logger.info("가격 기록: %s = %s (%s)", sku, price, channel)
        return entry

    def get_history(self, sku: str) -> list:
        """SKU 가격 이력 조회."""
        return self._history.get(sku, [])

    def get_change_rate(self, sku: str) -> float:
        """최근 가격 변동률 (%)."""
        history = self.get_history(sku)
        if len(history) < 2:
            return 0.0
        prev = Decimal(history[-2]['price'])
        curr = Decimal(history[-1]['price'])
        if prev == 0:
            return 0.0
        return float((curr - prev) / prev * 100)
