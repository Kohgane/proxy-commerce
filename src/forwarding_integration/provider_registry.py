"""src/forwarding_integration/provider_registry.py — 공급자 레지스트리/팩토리 (Phase 83)."""
from __future__ import annotations

import logging
from typing import Dict, List

from .providers.base import ForwardingProvider
from .providers.malltail import MalltailProvider
from .providers.ihanex import IHanexProvider
from .providers.ohmyzip import OhMyZipProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """배송대행 공급자 레지스트리.

    공급자 이름으로 조회하거나 새 공급자를 등록한다.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, ForwardingProvider] = {}
        # 기본 공급자 등록
        for provider in (MalltailProvider(), IHanexProvider(), OhMyZipProvider()):
            self.register(provider)

    def register(self, provider: ForwardingProvider) -> None:
        """공급자를 등록한다."""
        self._providers[provider.provider_id] = provider
        logger.debug('Provider registered: %s', provider.provider_id)

    def get(self, provider_id: str) -> ForwardingProvider:
        """공급자 ID로 공급자를 반환한다.

        Raises:
            KeyError: 등록되지 않은 공급자 ID인 경우.
        """
        provider = self._providers.get(provider_id)
        if provider is None:
            raise KeyError(f'Provider not found: {provider_id}')
        return provider

    def list_providers(self) -> List[Dict]:
        """등록된 모든 공급자 정보를 반환한다."""
        return [
            {'provider_id': p.provider_id, 'name': p.name}
            for p in self._providers.values()
        ]

    def provider_ids(self) -> List[str]:
        """등록된 공급자 ID 목록을 반환한다."""
        return list(self._providers.keys())


# 모듈 수준 기본 레지스트리 인스턴스
_default_registry: ProviderRegistry | None = None


def get_default_registry() -> ProviderRegistry:
    """기본 레지스트리 인스턴스를 반환한다 (지연 초기화)."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ProviderRegistry()
    return _default_registry
