"""
리소스 모니터링 — 메모리, 스레드, 캐시 사용률 추적.

stdlib resource 모듈 기반으로 외부 라이브러리 없이 동작한다.
"""

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """리소스 사용량 모니터링 유틸리티.

    메모리(RSS), 활성 스레드 수, 캐시 사용률을 측정한다.
    """

    def __init__(self, cache=None):
        """초기화.

        인자:
            cache: 캐시 객체 (src.cache 또는 src.utils 의 캐시). 없으면 캐시 메트릭 생략.
        """
        self._cache = cache

    # ── 메모리 ────────────────────────────────────────────────

    def get_memory_usage_mb(self) -> Optional[float]:
        """현재 프로세스의 RSS 메모리 사용량(MB)을 반환한다.

        반환:
            메모리 사용량(MB) 또는 측정 불가 시 None
        """
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            # ru_maxrss 단위: Linux=KB, macOS=bytes
            if os.uname().sysname == "Darwin":
                return usage.ru_maxrss / (1024 * 1024)
            return usage.ru_maxrss / 1024
        except Exception:  # noqa: BLE001
            try:
                # /proc/self/status 직접 읽기 (Linux)
                with open("/proc/self/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            return float(line.split()[1]) / 1024  # kB → MB
            except Exception:  # noqa: BLE001
                pass
            return None

    # ── 스레드 ────────────────────────────────────────────────

    def get_active_thread_count(self) -> int:
        """현재 활성 스레드 수를 반환한다."""
        return threading.active_count()

    # ── 캐시 ──────────────────────────────────────────────────

    def get_cache_stats(self) -> Optional[dict]:
        """캐시 사용률 정보를 반환한다.

        반환:
            'size', 'max_size', 'usage_pct' 키를 포함하는 딕셔너리 또는 None
        """
        if self._cache is None:
            return None

        try:
            # src.utils.cache.MemoryCache 호환 인터페이스
            size = len(self._cache) if hasattr(self._cache, "__len__") else None
            max_size = getattr(self._cache, "max_size", None)
            if size is None or max_size is None:
                return None
            return {
                "size": size,
                "max_size": max_size,
                "usage_pct": round(size / max_size * 100, 1) if max_size else 0.0,
            }
        except Exception:  # noqa: BLE001
            return None

    # ── 종합 요약 ─────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """현재 리소스 사용 현황 스냅샷을 반환한다.

        반환:
            'memory_mb', 'active_threads', 'cache' 키를 포함하는 딕셔너리
        """
        return {
            "memory_mb": self.get_memory_usage_mb(),
            "active_threads": self.get_active_thread_count(),
            "cache": self.get_cache_stats(),
        }

    def __repr__(self) -> str:
        snap = self.get_snapshot()
        mem = snap["memory_mb"]
        threads = snap["active_threads"]
        return f"<ResourceMonitor memory={mem}MB threads={threads}>"
