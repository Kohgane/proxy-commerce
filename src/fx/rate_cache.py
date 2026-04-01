"""TTL 기반 환율 캐시 (확장판).

기존 FXCache를 보완하는 경량 TTL 캐시로,
실시간 환율 서비스(RealtimeRates)와 함께 사용합니다.
"""

import logging
import os
import time
from decimal import Decimal
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 1800  # 30분


class RateCache:
    """TTL 기반 환율 캐시.

    기본 TTL 30분(configurable).
    통화쌍별로 독립 TTL을 관리합니다.
    """

    def __init__(self, ttl_seconds: int = None):
        """초기화.

        Args:
            ttl_seconds: 캐시 유효 시간(초). None이면 FX_CACHE_TTL_SECONDS 환경변수 또는 1800초.
        """
        self._ttl = ttl_seconds if ttl_seconds is not None else int(
            os.getenv('FX_CACHE_TTL_SECONDS', str(_DEFAULT_TTL))
        )
        # {pair: (rate, stored_at)}
        self._store: Dict[str, Tuple[Decimal, float]] = {}

    # ── public API ───────────────────────────────────────────

    def get(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        """환율 조회. 캐시 미스 또는 만료 시 None 반환.

        Args:
            from_currency: 원본 통화 코드 (예: 'USD')
            to_currency: 대상 통화 코드 (예: 'KRW')

        Returns:
            캐시된 환율 또는 None
        """
        key = self._make_key(from_currency, to_currency)
        entry = self._store.get(key)
        if entry is None:
            return None
        rate, stored_at = entry
        if (time.monotonic() - stored_at) >= self._ttl:
            del self._store[key]
            return None
        return rate

    def set(self, from_currency: str, to_currency: str, rate: Decimal):
        """환율 캐시 저장.

        Args:
            from_currency: 원본 통화 코드
            to_currency: 대상 통화 코드
            rate: 환율 값
        """
        key = self._make_key(from_currency, to_currency)
        self._store[key] = (rate, time.monotonic())
        logger.debug("RateCache set %s → %s: %s", from_currency, to_currency, rate)

    def invalidate(self, from_currency: str = None, to_currency: str = None):
        """캐시 무효화.

        Args:
            from_currency: 특정 통화쌍만 무효화 (None이면 전체)
            to_currency: 특정 통화쌍만 무효화 (None이면 전체)
        """
        if from_currency and to_currency:
            key = self._make_key(from_currency, to_currency)
            self._store.pop(key, None)
        else:
            self._store.clear()

    def is_valid(self, from_currency: str, to_currency: str) -> bool:
        """특정 통화쌍 캐시 유효 여부 확인.

        Args:
            from_currency: 원본 통화 코드
            to_currency: 대상 통화 코드

        Returns:
            캐시 유효 여부
        """
        return self.get(from_currency, to_currency) is not None

    def ttl_remaining(self, from_currency: str, to_currency: str) -> float:
        """남은 TTL(초) 반환. 캐시 없으면 0.0.

        Args:
            from_currency: 원본 통화 코드
            to_currency: 대상 통화 코드

        Returns:
            남은 TTL(초)
        """
        key = self._make_key(from_currency, to_currency)
        entry = self._store.get(key)
        if entry is None:
            return 0.0
        _, stored_at = entry
        remaining = self._ttl - (time.monotonic() - stored_at)
        return max(0.0, remaining)

    def size(self) -> int:
        """유효한 캐시 항목 수 반환."""
        now = time.monotonic()
        return sum(1 for _, (_, stored_at) in self._store.items()
                   if (now - stored_at) < self._ttl)

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _make_key(from_currency: str, to_currency: str) -> str:
        """통화쌍 캐시 키 생성."""
        return f"{from_currency.upper()}_{to_currency.upper()}"
