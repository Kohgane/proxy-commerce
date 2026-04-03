"""src/integrations/connection_health_check.py — 연결 상태 확인."""
from __future__ import annotations

from typing import Dict

from .integration_registry import IntegrationRegistry


class ConnectionHealthCheck:
    """모든 연동 연결 상태 확인."""

    def check_all(self, registry: IntegrationRegistry) -> Dict[str, dict]:
        results = {}
        for name in registry.list_all():
            connector = registry.get(name)
            if connector:
                try:
                    results[name] = connector.health_check()
                except Exception as exc:
                    results[name] = {"name": name, "status": "error", "error": str(exc)}
        return results

    def check_one(self, connector_name: str, registry: IntegrationRegistry) -> dict:
        connector = registry.get(connector_name)
        if connector is None:
            return {"name": connector_name, "status": "not_found"}
        try:
            return connector.health_check()
        except Exception as exc:
            return {"name": connector_name, "status": "error", "error": str(exc)}
