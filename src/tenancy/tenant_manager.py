"""src/tenancy/tenant_manager.py — 테넌트 CRUD."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TenantManager:
    """테넌트 생성/조회/수정/비활성화."""

    def __init__(self):
        self._tenants: Dict[str, dict] = {}

    def create(self, name: str, plan: str = 'free', config: Optional[dict] = None) -> dict:
        tenant_id = str(uuid.uuid4())[:8]
        tenant = {
            'id': tenant_id,
            'name': name,
            'status': 'active',
            'plan': plan,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'config': config or {},
        }
        self._tenants[tenant_id] = tenant
        logger.info("테넌트 생성: %s (%s)", tenant_id, name)
        return tenant

    def get(self, tenant_id: str) -> Optional[dict]:
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> List[dict]:
        return list(self._tenants.values())

    def update(self, tenant_id: str, **kwargs) -> dict:
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise KeyError(f"테넌트 없음: {tenant_id}")
        for key in ('name', 'plan', 'config'):
            if key in kwargs:
                tenant[key] = kwargs[key]
        return tenant

    def deactivate(self, tenant_id: str) -> dict:
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise KeyError(f"테넌트 없음: {tenant_id}")
        tenant['status'] = 'inactive'
        return tenant
