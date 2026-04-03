"""src/tenancy/tenant_isolation.py — 테넌트 데이터 격리."""
import logging
from typing import List

logger = logging.getLogger(__name__)


class TenantIsolation:
    """테넌트별 데이터 격리 유틸리티."""

    def filter_by_tenant(self, items: List[dict], tenant_id: str) -> List[dict]:
        """tenant_id 필드로 필터링."""
        return [item for item in items if item.get('tenant_id') == tenant_id]

    def add_tenant_id(self, item: dict, tenant_id: str) -> dict:
        """아이템에 tenant_id 추가."""
        item['tenant_id'] = tenant_id
        return item
