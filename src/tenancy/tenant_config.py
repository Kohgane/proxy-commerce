"""src/tenancy/tenant_config.py — 테넌트별 독립 설정."""
from __future__ import annotations

from typing import Dict, Optional


_DEFAULT_CONFIG = {
    "margin_rate": 0.20,
    "fx_strategy": "live",
    "shipping_policy": "standard",
    "notification_channels": ["telegram"],
    "currency": "KRW",
    "locale": "ko",
}


class TenantConfig:
    """테넌트별 마진율, 환율 전략, 배송비 정책, 알림 설정 관리."""

    def __init__(self) -> None:
        self._configs: Dict[str, dict] = {}

    def set(self, tenant_id: str, **kwargs) -> dict:
        """설정 저장 (없으면 기본값으로 초기화 후 업데이트)."""
        if tenant_id not in self._configs:
            self._configs[tenant_id] = dict(_DEFAULT_CONFIG)
        self._configs[tenant_id].update(kwargs)
        return dict(self._configs[tenant_id])

    def get(self, tenant_id: str) -> dict:
        """테넌트 설정 조회 (없으면 기본값)."""
        return dict(self._configs.get(tenant_id, _DEFAULT_CONFIG))

    def get_field(self, tenant_id: str, field: str, default=None):
        """특정 설정 필드 조회."""
        return self.get(tenant_id).get(field, default)

    def reset(self, tenant_id: str) -> dict:
        """기본값으로 초기화."""
        self._configs[tenant_id] = dict(_DEFAULT_CONFIG)
        return dict(self._configs[tenant_id])

    def delete(self, tenant_id: str) -> bool:
        """테넌트 설정 삭제."""
        if tenant_id in self._configs:
            del self._configs[tenant_id]
            return True
        return False
