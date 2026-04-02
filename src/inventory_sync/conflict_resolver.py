"""재고 충돌 해소기."""

import logging

logger = logging.getLogger(__name__)

STRATEGY_LAST_WRITE_WINS = 'last_write_wins'
STRATEGY_CONSERVATIVE = 'conservative'


class ConflictResolver:
    """채널 간 재고 충돌 해소."""

    def __init__(self, strategy: str = STRATEGY_CONSERVATIVE):
        self.strategy = strategy

    def resolve(self, sku: str, channel_stocks: dict) -> int:
        """채널별 재고에서 최종 재고 결정.

        Args:
            sku: 상품 SKU
            channel_stocks: {channel_name: stock_qty} 딕셔너리

        Returns:
            결정된 재고 수량
        """
        if not channel_stocks:
            return 0

        values = list(channel_stocks.values())

        if self.strategy == STRATEGY_LAST_WRITE_WINS:
            result = values[-1]
        else:
            result = min(values)

        logger.debug("충돌 해소 [%s] %s: %s -> %d", self.strategy, sku, channel_stocks, result)
        return result
