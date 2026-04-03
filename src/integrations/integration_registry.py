"""src/integrations/integration_registry.py — 연동 레지스트리."""
from __future__ import annotations

from typing import Dict, List, Optional

from .integration_connector import IntegrationConnector


class IntegrationRegistry:
    """연동 커넥터 등록 및 관리."""

    def __init__(self) -> None:
        self._connectors: Dict[str, IntegrationConnector] = {}
        self._active: Dict[str, bool] = {}

    def register(self, connector: IntegrationConnector) -> None:
        self._connectors[connector.name] = connector
        self._active[connector.name] = False

    def unregister(self, name: str) -> None:
        self._connectors.pop(name, None)
        self._active.pop(name, None)

    def get(self, name: str) -> Optional[IntegrationConnector]:
        return self._connectors.get(name)

    def list_all(self) -> List[str]:
        return list(self._connectors.keys())

    def list_active(self) -> List[str]:
        return [name for name, active in self._active.items() if active]

    def set_active(self, name: str, active: bool) -> None:
        if name in self._connectors:
            self._active[name] = active
