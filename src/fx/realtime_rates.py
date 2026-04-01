"""실시간 환율 조회 서비스.

한국수출입은행 API를 기본으로 사용하고,
실패 시 exchangerate-api.com으로 fallback합니다.
결과는 RateCache로 TTL 기반 캐싱합니다.
"""

import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests

from .rate_cache import RateCache
from .supported_currencies import DEFAULT_RATES_TO_KRW, SUPPORTED_CURRENCIES

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 10
_DEFAULT_CACHE_TTL = 1800  # 30분


class RealtimeRates:
    """실시간 환율 조회 서비스.

    우선순위:
      1) 한국수출입은행 API (KOREAEXIM_API_KEY 필요)
      2) exchangerate-api.com (EXCHANGERATE_API_KEY 필요)
      3) 하드코딩된 기본값 fallback

    모든 환율은 KRW 기준으로 조회/변환합니다.
    """

    PROVIDER_KOREAEXIM = 'koreaexim'
    PROVIDER_EXCHANGERATE = 'exchangerate-api'
    PROVIDER_FALLBACK = 'fallback'

    _KOREAEXIM_URL = 'https://www.koreaexim.go.kr/site/program/financial/exchangeJSON'
    _EXCHANGERATE_URL = 'https://v6.exchangerate-api.com/v6/{key}/latest/KRW'

    def __init__(self, cache: RateCache = None, cache_ttl: int = None):
        """초기화.

        Args:
            cache: RateCache 인스턴스. None이면 새로 생성.
            cache_ttl: 캐시 TTL(초). None이면 FX_CACHE_TTL_SECONDS 환경변수 또는 1800초.
        """
        ttl = cache_ttl if cache_ttl is not None else int(
            os.getenv('FX_CACHE_TTL_SECONDS', str(_DEFAULT_CACHE_TTL))
        )
        self._cache = cache if cache is not None else RateCache(ttl_seconds=ttl)

    # ── public API ───────────────────────────────────────────

    def get_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """실시간 환율 조회.

        Args:
            from_currency: 원본 통화 (예: 'USD')
            to_currency: 대상 통화 (예: 'KRW')

        Returns:
            환율 (Decimal)

        Raises:
            ValueError: 지원하지 않는 통화 코드인 경우
        """
        from_c = from_currency.upper()
        to_c = to_currency.upper()

        if from_c not in SUPPORTED_CURRENCIES and from_c != 'KRW':
            raise ValueError(f"지원하지 않는 통화: {from_currency}")
        if to_c not in SUPPORTED_CURRENCIES and to_c != 'KRW':
            raise ValueError(f"지원하지 않는 통화: {to_currency}")

        # 동일 통화
        if from_c == to_c:
            return Decimal('1')

        # 캐시 확인
        cached = self._cache.get(from_c, to_c)
        if cached is not None:
            return cached

        # 실시간 조회
        rate = self._fetch_rate(from_c, to_c)
        self._cache.set(from_c, to_c, rate)
        return rate

    def convert(self, amount: float, from_currency: str, to_currency: str) -> Decimal:
        """금액 환율 변환.

        Args:
            amount: 변환할 금액
            from_currency: 원본 통화
            to_currency: 대상 통화

        Returns:
            변환된 금액 (Decimal)
        """
        rate = self.get_rate(from_currency, to_currency)
        return Decimal(str(amount)) * rate

    def get_rates_to_krw(self) -> dict:
        """KRW 기준 모든 지원 통화 환율 조회.

        Returns:
            {통화코드: Decimal(환율)} 딕셔너리
        """
        result = {}
        for currency in SUPPORTED_CURRENCIES:
            if currency == 'KRW':
                result['KRW'] = Decimal('1')
                continue
            try:
                result[currency] = self.get_rate(currency, 'KRW')
            except Exception as exc:
                logger.warning("get_rates_to_krw: %s 조회 실패: %s", currency, exc)
                result[currency] = Decimal(str(DEFAULT_RATES_TO_KRW.get(currency, 0)))
        return result

    def invalidate_cache(self, from_currency: str = None, to_currency: str = None):
        """캐시 무효화.

        Args:
            from_currency: 특정 통화쌍 무효화. None이면 전체 무효화.
            to_currency: 특정 통화쌍 무효화. None이면 전체 무효화.
        """
        self._cache.invalidate(from_currency, to_currency)

    # ── 내부 조회 로직 ────────────────────────────────────────

    def _fetch_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """환율 조회 (provider 순서대로 시도)."""
        providers = [
            (self.PROVIDER_KOREAEXIM, self._fetch_from_koreaexim),
            (self.PROVIDER_EXCHANGERATE, self._fetch_from_exchangerate),
        ]
        for provider_name, fetch_fn in providers:
            try:
                rate = fetch_fn(from_currency, to_currency)
                if rate is not None:
                    logger.info("환율 조회 성공 [%s]: %s/%s = %s", provider_name, from_currency, to_currency, rate)
                    return rate
            except Exception as exc:
                logger.warning("환율 조회 실패 [%s]: %s", provider_name, exc)

        # fallback: 기본값
        return self._get_fallback_rate(from_currency, to_currency)

    def _fetch_from_koreaexim(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        """한국수출입은행 API에서 환율 조회."""
        api_key = os.getenv('KOREAEXIM_API_KEY', '')
        if not api_key:
            logger.debug("KOREAEXIM_API_KEY 미설정 — 한국수출입은행 API 건너뜀")
            return None

        from datetime import date
        search_date = date.today().strftime('%Y%m%d')
        params = {
            'authkey': api_key,
            'searchdate': search_date,
            'data': 'AP01',
        }
        resp = requests.get(self._KOREAEXIM_URL, params=params, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return None

        # KRW 기준 환율 파싱
        rate_map: dict = {}
        for item in data:
            cur_unit = str(item.get('cur_unit', '')).replace('(100)', '').strip()
            ttb = str(item.get('ttb', '')).replace(',', '')  # 살 때 환율
            tts = str(item.get('tts', '')).replace(',', '')  # 팔 때 환율
            try:
                # 매매기준율(deal_bas_r) 사용
                deal_bas = str(item.get('deal_bas_r', '')).replace(',', '')
                rate_map[cur_unit] = Decimal(deal_bas)
                # JPY는 100엔 단위이므로 100으로 나눔
                if '(100)' in str(item.get('cur_unit', '')):
                    rate_map[cur_unit] = Decimal(deal_bas) / Decimal('100')
            except (InvalidOperation, Exception):
                pass
            _ = ttb, tts  # suppress unused warning

        return self._resolve_rate(from_currency, to_currency, rate_map)

    def _fetch_from_exchangerate(self, from_currency: str, to_currency: str) -> Optional[Decimal]:
        """exchangerate-api.com에서 환율 조회."""
        api_key = os.getenv('EXCHANGERATE_API_KEY', '')
        if not api_key:
            logger.debug("EXCHANGERATE_API_KEY 미설정 — exchangerate-api 건너뜀")
            return None

        # from_currency 기준 환율 조회
        url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/{from_currency}"
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get('result') != 'success':
            raise ValueError(f"exchangerate-api 오류: {data.get('error-type')}")
        rates = data.get('conversion_rates', {})
        rate_val = rates.get(to_currency)
        if rate_val is None:
            return None
        return Decimal(str(rate_val))

    def _get_fallback_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """기본값 기반 fallback 환율."""
        logger.warning("환율 fallback 사용: %s → %s", from_currency, to_currency)
        if to_currency == 'KRW':
            return Decimal(str(DEFAULT_RATES_TO_KRW.get(from_currency, 1.0)))
        if from_currency == 'KRW':
            krw_rate = DEFAULT_RATES_TO_KRW.get(to_currency, 1.0)
            if krw_rate == 0:
                return Decimal('0')
            return Decimal('1') / Decimal(str(krw_rate))
        # 교차 환율: from → KRW → to
        from_krw = Decimal(str(DEFAULT_RATES_TO_KRW.get(from_currency, 1.0)))
        to_krw = Decimal(str(DEFAULT_RATES_TO_KRW.get(to_currency, 1.0)))
        if to_krw == 0:
            return Decimal('0')
        return from_krw / to_krw

    @staticmethod
    def _resolve_rate(from_currency: str, to_currency: str, rate_map: dict) -> Optional[Decimal]:
        """KRW 기준 rate_map에서 원하는 환율 계산.

        Args:
            from_currency: 원본 통화
            to_currency: 대상 통화
            rate_map: {통화코드: KRW당 환율}

        Returns:
            계산된 환율 또는 None
        """
        if to_currency == 'KRW' and from_currency in rate_map:
            return rate_map[from_currency]
        if from_currency == 'KRW' and to_currency in rate_map:
            krw_rate = rate_map[to_currency]
            if krw_rate == 0:
                return None
            return Decimal('1') / krw_rate
        # 교차 환율
        if from_currency in rate_map and to_currency in rate_map:
            to_krw_rate = rate_map[to_currency]
            if to_krw_rate == 0:
                return None
            return rate_map[from_currency] / to_krw_rate
        return None
