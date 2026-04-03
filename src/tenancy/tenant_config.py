"""src/tenancy/tenant_config.py — 테넌트별 설정."""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class TenantConfig:
    """테넌트별 설정 관리."""

    _DEFAULTS = {
        'margin_rate': 0.2,
        'currency_strategy': 'fixed',
        'shipping_policy': 'standard',
        'notification_settings': {},
    }

    def __init__(self):
        self._configs: Dict[str, dict] = {}

    def get_config(self, tenant_id: str) -> dict:
        return self._configs.get(tenant_id, dict(self._DEFAULTS))

    def set_config(self, tenant_id: str, **kwargs) -> dict:
        config = self._configs.setdefault(tenant_id, dict(self._DEFAULTS))
        for key in ('margin_rate', 'currency_strategy', 'shipping_policy', 'notification_settings'):
            if key in kwargs:
                config[key] = kwargs[key]
        return config

    def update_config(self, tenant_id: str, **kwargs) -> dict:
        return self.set_config(tenant_id, **kwargs)
