"""src/fx/exchange_rate_api.py — ExchangeRate-API v6 통합 (Phase 128).

기능:
- ExchangeRate-API v6 엔드포인트 호출 (https://v6.exchangerate-api.com/v6/{KEY}/latest/KRW)
- API 키 없으면 환경변수 FX_USDKRW 등 폴백
- 5분 메모리 캐시
- FX_DISABLE_NETWORK=1 이면 네트워크 호출 X

환경변수:
  EXCHANGE_RATE_API_KEY   — ExchangeRate-API v6 키
  FX_DISABLE_NETWORK      — 1 이면 네트워크 호출 비활성화
  FX_USDKRW               — 폴백 USD/KRW 환율
  FX_JPYKRW               — 폴백 JPY/KRW 환율
  FX_EURKRW               — 폴백 EUR/KRW 환율
  FX_CNYKRW               — 폴백 CNY/KRW 환율
"""
from __future__ import annotations

import logging
import os
import time
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)

# 캐시 TTL — 5분
_CACHE_TTL_SECONDS = 300

# 기본 폴백 환율 (KRW 기준)
_FALLBACK_RATES: dict = {
    "USD": Decimal("1350"),
    "JPY": Decimal("9.0"),
    "EUR": Decimal("1480"),
    "CNY": Decimal("186"),
    "GBP": Decimal("1710"),
    "KRW": Decimal("1"),
}

# 메모리 캐시: {통화코드: (rate, timestamp)}
_rate_cache: dict = {}


def _env_fallback_rates() -> dict:
    """환경변수 FX_USDKRW 등에서 폴백 환율을 읽어 반환."""
    rates = dict(_FALLBACK_RATES)
    env_map = {
        "USD": "FX_USDKRW",
        "JPY": "FX_JPYKRW",
        "EUR": "FX_EURKRW",
        "CNY": "FX_CNYKRW",
        "GBP": "FX_GBPKRW",
    }
    for cur, env_key in env_map.items():
        val = os.getenv(env_key)
        if val:
            try:
                rates[cur] = Decimal(val.strip())
            except InvalidOperation:
                pass
    return rates


def _is_cache_valid(currency: str) -> bool:
    """캐시가 유효한지 확인 (TTL 이내)."""
    entry = _rate_cache.get(currency)
    if entry is None:
        return False
    _, ts = entry
    return (time.time() - ts) < _CACHE_TTL_SECONDS


def _get_cached(currency: str) -> Optional[Decimal]:
    """캐시에서 환율 조회."""
    entry = _rate_cache.get(currency)
    if entry is None:
        return None
    rate, _ = entry
    return rate


def _set_cache(currency: str, rate: Decimal) -> None:
    """캐시에 환율 저장."""
    _rate_cache[currency] = (rate, time.time())


def _fetch_from_api(base: str = "KRW") -> Optional[dict]:
    """ExchangeRate-API v6에서 환율 데이터 fetch.

    Args:
        base: 기준 통화 (기본값: KRW)

    Returns:
        {통화코드: rate} dict, 또는 None (실패 시)
    """
    if os.getenv("FX_DISABLE_NETWORK", "0") == "1":
        logger.debug("FX_DISABLE_NETWORK=1 — ExchangeRate-API 호출 건너뜀")
        return None

    api_key = os.getenv("EXCHANGE_RATE_API_KEY", "").strip()
    if not api_key:
        logger.debug("EXCHANGE_RATE_API_KEY 미설정 — ExchangeRate-API 건너뜀")
        return None

    # API 키를 URL 경로에 포함 (ExchangeRate-API v6 규격)
    url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}"
    safe_url_prefix = "https://v6.exchangerate-api.com/v6/***"  # 로그용 마스킹
    try:
        import requests
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result") != "success":
            logger.warning("ExchangeRate-API 오류: %s", data.get("error-type"))
            return None
        return data.get("conversion_rates", {})
    except Exception as exc:
        # URL 로그 시 API 키 마스킹 — exc 메시지에 URL이 포함되지 않도록 type만 로그
        logger.warning("ExchangeRate-API fetch 실패 (base=%s, error=%s: %s)", base, type(exc).__name__, str(exc).split("api_key")[0][:80])
        return None


def get_rate_to_krw(currency: str) -> Decimal:
    """특정 통화 → KRW 환율 반환.

    우선순위:
      1) 5분 이내 캐시
      2) ExchangeRate-API v6 (API 키 + 네트워크 활성 시)
      3) 환경변수 FX_USDKRW 등 폴백
      4) 하드코딩된 기본값

    Args:
        currency: 통화 코드 (예: 'USD', 'JPY')

    Returns:
        KRW 환율 (Decimal)
    """
    cur = currency.upper()

    if cur == "KRW":
        return Decimal("1")

    # 캐시 확인
    if _is_cache_valid(cur):
        rate = _get_cached(cur)
        if rate is not None:
            logger.debug("환율 캐시 사용: %s/KRW = %s", cur, rate)
            return rate

    # API 호출 (KRW 기준 latest 조회)
    rates_raw = _fetch_from_api(base="KRW")
    if rates_raw:
        # KRW → currency 비율을 역수로 변환 → currency → KRW
        # API: KRW latest → {USD: 0.00074, JPY: 0.109, ...}
        # 즉 1 KRW = X currency → 1 currency = 1/X KRW
        for code, raw_val in rates_raw.items():
            try:
                val = Decimal(str(raw_val))
                if val > 0:
                    rate_to_krw = Decimal("1") / val
                    _set_cache(code, rate_to_krw)
            except (InvalidOperation, Exception):
                pass

        # 갱신된 캐시에서 다시 조회
        if _is_cache_valid(cur):
            rate = _get_cached(cur)
            if rate is not None:
                logger.info("ExchangeRate-API 환율 업데이트: %s/KRW = %s", cur, rate)
                return rate

    # 폴백
    fallback = _env_fallback_rates()
    rate = fallback.get(cur, _FALLBACK_RATES.get(cur, Decimal("1")))
    logger.warning("환율 폴백 사용: %s/KRW = %s", cur, rate)
    return rate


def get_rates_summary() -> dict:
    """주요 통화 환율 요약 반환.

    Returns:
        {currency: rate_str, ..., "source": "api"|"fallback", "cached_at": ts}
    """
    currencies = ["USD", "JPY", "EUR", "CNY"]
    result = {}
    source = "fallback"

    for cur in currencies:
        rate = get_rate_to_krw(cur)
        result[cur] = str(rate)

    # 캐시에서 소스 판단
    if any(_is_cache_valid(c) for c in currencies):
        source = "api"

    result["source"] = source
    result["cache_ttl_seconds"] = _CACHE_TTL_SECONDS
    return result


def invalidate_cache() -> None:
    """전체 캐시 무효화."""
    _rate_cache.clear()
    logger.debug("ExchangeRate 캐시 무효화")
