"""src/tenancy/tenant_isolation.py — 테넌트 데이터 격리."""
from __future__ import annotations

from typing import Any, Dict, List


class TenantIsolation:
    """테넌트 ID 기반 데이터 격리 및 필터링."""

    def filter(self, records: List[dict], tenant_id: str) -> List[dict]:
        """테넌트 ID로 레코드 필터링."""
        return [r for r in records if r.get("tenant_id") == tenant_id]

    def tag(self, record: dict, tenant_id: str) -> dict:
        """레코드에 tenant_id 태그 추가."""
        tagged = dict(record)
        tagged["tenant_id"] = tenant_id
        return tagged

    def tag_many(self, records: List[dict], tenant_id: str) -> List[dict]:
        """여러 레코드에 tenant_id 태그 추가."""
        return [self.tag(r, tenant_id) for r in records]

    def validate_access(self, record: dict, tenant_id: str) -> bool:
        """레코드가 해당 테넌트 소유인지 검증."""
        return record.get("tenant_id") == tenant_id

    def strip_tag(self, record: dict) -> dict:
        """tenant_id 태그 제거 (내보내기 등에서 사용)."""
        result = dict(record)
        result.pop("tenant_id", None)
        return result
