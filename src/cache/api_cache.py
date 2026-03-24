"""src/cache/api_cache.py — API 응답 캐시 데코레이터.

Shopify, WooCommerce, 번역, 환율 등 외부 API 응답을 캐싱한다.
캐시 키는 함수명 + 인자의 해시로 생성한다.

사용 예:
    @cached(ttl=300, key_prefix="shopify")
    def get_products(shop_id: str):
        ...

환경변수:
  CACHE_ENABLED      — 캐시 활성화 여부 (기본 "1")
  CACHE_DEFAULT_TTL  — 기본 TTL 초 (기본 300)
"""

import functools
import hashlib
import json
import logging
import os
from typing import Any, Callable, Optional

from .memory_cache import MemoryCache

logger = logging.getLogger(__name__)

_DEFAULT_TTL = int(os.getenv("CACHE_DEFAULT_TTL", "300"))


# ──────────────────────────────────────────────────────────
# 모듈 전역 캐시 인스턴스
# ──────────────────────────────────────────────────────────

_global_cache = MemoryCache()


# ──────────────────────────────────────────────────────────
# 캐시 키 생성
# ──────────────────────────────────────────────────────────

def _make_cache_key(prefix: str, func_name: str, args: tuple, kwargs: dict) -> str:
    """함수명 + 인자 기반 캐시 키를 생성한다.

    Args:
        prefix: 캐시 키 접두어 (예: "shopify", "woo")
        func_name: 함수명
        args: 위치 인자 튜플
        kwargs: 키워드 인자 딕셔너리

    Returns:
        SHA256 기반 캐시 키 문자열
    """
    try:
        key_data = json.dumps({"args": list(args), "kwargs": kwargs}, sort_keys=True, default=str)
    except (TypeError, ValueError):
        key_data = str(args) + str(sorted(kwargs.items()))

    hash_val = hashlib.sha256(key_data.encode()).hexdigest()[:16]
    return f"{prefix}:{func_name}:{hash_val}"


# ──────────────────────────────────────────────────────────
# cached 데코레이터
# ──────────────────────────────────────────────────────────

def cached(
    ttl: int = _DEFAULT_TTL,
    key_prefix: str = "api",
    cache: Optional[MemoryCache] = None,
):
    """API 응답을 캐싱하는 데코레이터.

    Args:
        ttl: 캐시 유효 시간 초 (기본: CACHE_DEFAULT_TTL)
        key_prefix: 캐시 키 접두어 (기본 "api")
        cache: 사용할 MemoryCache 인스턴스 (None이면 전역 캐시 사용)

    사용 예:
        @cached(ttl=300, key_prefix="shopify")
        def fetch_products():
            ...
    """
    def decorator(func: Callable) -> Callable:
        target_cache = cache or _global_cache

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = _make_cache_key(key_prefix, func.__name__, args, kwargs)
            cached_value = target_cache.get(cache_key, ttl=ttl)
            if cached_value is not None:
                logger.debug("API 캐시 HIT: key=%s func=%s", cache_key, func.__name__)
                return cached_value

            result = func(*args, **kwargs)
            if result is not None:
                target_cache.set(cache_key, result, ttl=ttl)
                logger.debug("API 캐시 SET: key=%s func=%s ttl=%ds", cache_key, func.__name__, ttl)
            return result

        wrapper._cache = target_cache
        wrapper._cache_ttl = ttl
        wrapper._cache_prefix = key_prefix
        return wrapper

    return decorator


# ──────────────────────────────────────────────────────────
# ApiCache 클래스 (더 세밀한 제어가 필요한 경우)
# ──────────────────────────────────────────────────────────

class ApiCache:
    """API 별로 별도 캐시 인스턴스를 관리하는 캐시 매니저.

    사용 예:
        shopify_cache = ApiCache(name="shopify", ttl=300)
        data = shopify_cache.get_or_fetch("products", fetch_fn)
    """

    def __init__(self, name: str, ttl: int = _DEFAULT_TTL, max_size: int = 500):
        self.name = name
        self._cache = MemoryCache(ttl_seconds=ttl, max_size=max_size)

    def get_or_fetch(self, key: str, fetch_fn: Callable, ttl: Optional[int] = None) -> Any:
        """캐시에서 값을 조회하거나, 없으면 fetch_fn을 호출해 캐싱 후 반환한다.

        Args:
            key: 캐시 키
            fetch_fn: 캐시 미스 시 호출할 함수 (인자 없음)
            ttl: 이 항목의 TTL (None이면 기본 TTL 사용)

        Returns:
            fetch_fn의 반환값 (또는 캐시된 값)
        """
        full_key = f"{self.name}:{key}"
        cached_val = self._cache.get(full_key, ttl=ttl)
        if cached_val is not None:
            return cached_val

        result = fetch_fn()
        if result is not None:
            self._cache.set(full_key, result, ttl=ttl)
        return result

    def invalidate(self, key: str) -> bool:
        """특정 캐시 항목을 무효화한다."""
        return self._cache.delete(f"{self.name}:{key}")

    def clear(self):
        """전체 캐시를 비운다."""
        self._cache.clear()

    @property
    def stats(self):
        """캐시 통계를 반환한다."""
        return self._cache.stats
