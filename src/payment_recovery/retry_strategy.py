"""src/payment_recovery/retry_strategy.py — 재시도 전략."""
from __future__ import annotations


class RetryStrategy:
    """재시도 전략."""

    def __init__(self, strategy_type: str = 'immediate', interval: int = 300) -> None:
        self.strategy_type = strategy_type
        self.interval = interval

    def next_delay(self, attempt: int) -> int:
        """다음 지연 시간을 반환한다."""
        if self.strategy_type == 'immediate':
            return 0
        if self.strategy_type == 'exponential':
            return 60 * (2 ** (attempt - 1))
        # fixed
        return self.interval
