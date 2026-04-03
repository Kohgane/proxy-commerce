"""src/multicurrency/conversion.py — Phase 45: 통화 변환 엔진."""
import logging
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CACHE_TTL = 3600  # 1시간

# 기본 환율 (KRW 기준) — mock 값
DEFAULT_RATES: Dict[str, float] = {
    'KRW': 1.0,
    'USD': 1350.0,      # 1 USD = 1350 KRW
    'JPY': 9.0,         # 1 JPY = 9 KRW
    'CNY': 185.0,       # 1 CNY = 185 KRW
    'EUR': 1480.0,      # 1 EUR = 1480 KRW
}

ROUNDING_RULES: Dict[str, int] = {
    'KRW': 0,
    'JPY': 0,
    'USD': 2,
    'EUR': 2,
    'CNY': 2,
}


class CurrencyConverter:
    """환율 기반 통화 변환.

    - 환율 캐시 (TTL 1시간)
    - 통화별 라운딩 규칙
    """

    def __init__(self, rates: Optional[Dict[str, float]] = None):
        # rates: {currency_code: rate_to_KRW}
        self._rates: Dict[str, float] = dict(DEFAULT_RATES)
        if rates:
            self._rates.update(rates)
        self._cache_time: float = time.time()

    def update_rates(self, rates: Dict[str, float]):
        """환율 업데이트 + 캐시 갱신."""
        self._rates.update(rates)
        self._cache_time = time.time()
        logger.info("환율 업데이트: %d 통화", len(rates))

    def is_cache_valid(self) -> bool:
        return (time.time() - self._cache_time) < CACHE_TTL

    def convert(self, amount: float, from_currency: str, to_currency: str) -> float:
        """통화 변환.

        KRW 기준 환율을 사용하여 변환.
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        if from_currency == to_currency:
            return amount
        rate_from = self._rates.get(from_currency)
        rate_to = self._rates.get(to_currency)
        if rate_from is None:
            raise ValueError(f"환율 없음: {from_currency}")
        if rate_to is None:
            raise ValueError(f"환율 없음: {to_currency}")
        # amount → KRW → to_currency
        krw_amount = Decimal(str(amount)) * Decimal(str(rate_from))
        result = krw_amount / Decimal(str(rate_to))
        decimals = ROUNDING_RULES.get(to_currency, 2)
        quantize_str = '1' if decimals == 0 else '0.' + '0' * decimals
        result = result.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)
        return float(result)

    def get_rate(self, from_currency: str, to_currency: str) -> float:
        """두 통화 간 환율 반환 (1 from = ? to)."""
        return self.convert(1.0, from_currency, to_currency)
