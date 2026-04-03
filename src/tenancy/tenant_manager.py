"""src/tenancy/tenant_manager.py — 테넌트 CRUD 관리."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class TenantManager:
    """테넌트 생성/조회/업데이트/비활성화."""

    def __init__(self) -> None:
        self._tenants: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    def create(self, name: str, owner_email: str, plan: str = "free", **kwargs) -> dict:
        """새 테넌트 생성."""
        if not name or not owner_email:
            raise ValueError("name과 owner_email은 필수입니다.")
        tenant_id = kwargs.get("tenant_id") or str(uuid.uuid4())
        if tenant_id in self._tenants:
            raise ValueError(f"이미 존재하는 테넌트 ID: {tenant_id}")
        tenant = {
            "tenant_id": tenant_id,
            "name": name,
            "owner_email": owner_email,
            "plan": plan,
            "active": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            **{k: v for k, v in kwargs.items() if k != "tenant_id"},
        }
        self._tenants[tenant_id] = tenant
        return dict(tenant)

    def get(self, tenant_id: str) -> Optional[dict]:
        """테넌트 조회."""
        t = self._tenants.get(tenant_id)
        return dict(t) if t else None

    def list(self, active_only: bool = False) -> List[dict]:
        """테넌트 목록."""
        tenants = list(self._tenants.values())
        if active_only:
            tenants = [t for t in tenants if t.get("active")]
        return [dict(t) for t in tenants]

    def update(self, tenant_id: str, **kwargs) -> dict:
        """테넌트 정보 업데이트."""
        if tenant_id not in self._tenants:
            raise KeyError(f"테넌트 없음: {tenant_id}")
        for key, value in kwargs.items():
            if key not in ("tenant_id", "created_at"):
                self._tenants[tenant_id][key] = value
        self._tenants[tenant_id]["updated_at"] = _now_iso()
        return dict(self._tenants[tenant_id])

    def deactivate(self, tenant_id: str) -> dict:
        """테넌트 비활성화."""
        if tenant_id not in self._tenants:
            raise KeyError(f"테넌트 없음: {tenant_id}")
        self._tenants[tenant_id]["active"] = False
        self._tenants[tenant_id]["updated_at"] = _now_iso()
        return dict(self._tenants[tenant_id])

    def delete(self, tenant_id: str) -> bool:
        """테넌트 삭제."""
        if tenant_id not in self._tenants:
            return False
        del self._tenants[tenant_id]
        return True
