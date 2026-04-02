"""src/scheduler/job_registry.py — Phase 40: 작업 등록 레지스트리."""
import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_global_registry: Dict[str, Callable] = {}


def register_job(name: Optional[str] = None):
    """@register_job 데코레이터 — 함수를 전역 레지스트리에 등록."""
    def decorator(func: Callable) -> Callable:
        job_name = name or func.__name__
        _global_registry[job_name] = func
        logger.debug("작업 등록: %s", job_name)
        return func
    return decorator


class JobRegistry:
    """이름 → callable 매핑 레지스트리."""

    def __init__(self, use_global: bool = True):
        self._registry: Dict[str, Callable] = {}
        if use_global:
            self._registry.update(_global_registry)

    def register(self, name: str, func: Callable) -> None:
        """작업 등록."""
        self._registry[name] = func
        logger.info("JobRegistry 등록: %s", name)

    def get(self, name: str) -> Optional[Callable]:
        """이름으로 작업 조회."""
        return self._registry.get(name)

    def list_names(self) -> List[str]:
        """등록된 작업 이름 목록."""
        return list(self._registry.keys())

    def unregister(self, name: str) -> bool:
        """작업 등록 해제."""
        if name in self._registry:
            del self._registry[name]
            return True
        return False

    def __contains__(self, name: str) -> bool:
        return name in self._registry
