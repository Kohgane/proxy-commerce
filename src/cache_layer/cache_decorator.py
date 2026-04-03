"""src/cache_layer/cache_decorator.py — 캐시 데코레이터."""
from __future__ import annotations

import functools
from typing import Any, Callable, Optional

from .cache_manager import CacheManager

_default_manager = CacheManager()


def cached(ttl: int = 300, manager: Optional[CacheManager] = None):
    """함수 결과를 캐시하는 데코레이터."""
    cm = manager or _default_manager

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            key = f"{fn.__module__}.{fn.__qualname__}:{args}:{sorted(kwargs.items())}"
            cached_val = cm.get(key)
            if cached_val is not None:
                return cached_val
            result = fn(*args, **kwargs)
            cm.set(key, result, ttl=ttl)
            return result
        return wrapper
    return decorator
