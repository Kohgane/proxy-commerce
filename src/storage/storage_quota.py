"""src/storage/storage_quota.py — 스토리지 할당량 관리."""
from __future__ import annotations

from typing import Dict


class StorageQuota:
    """사용자별 스토리지 할당량 관리."""

    DEFAULT_QUOTA_BYTES = 1024 * 1024 * 1024  # 1 GB

    def __init__(self) -> None:
        self._quotas: Dict[str, int] = {}
        self._usage: Dict[str, int] = {}

    def set_quota(self, owner_id: str, bytes_limit: int) -> None:
        self._quotas[owner_id] = bytes_limit

    def get_quota(self, owner_id: str) -> int:
        return self._quotas.get(owner_id, self.DEFAULT_QUOTA_BYTES)

    def get_usage(self, owner_id: str) -> int:
        return self._usage.get(owner_id, 0)

    def check_quota(self, owner_id: str, size: int) -> bool:
        """업로드 가능 여부 확인. True면 허용."""
        return self.get_usage(owner_id) + size <= self.get_quota(owner_id)

    def record_upload(self, owner_id: str, size: int) -> None:
        self._usage[owner_id] = self._usage.get(owner_id, 0) + size

    def record_delete(self, owner_id: str, size: int) -> None:
        current = self._usage.get(owner_id, 0)
        self._usage[owner_id] = max(0, current - size)

    def get_summary(self, owner_id: str) -> dict:
        usage = self.get_usage(owner_id)
        quota = self.get_quota(owner_id)
        return {
            "owner_id": owner_id,
            "usage_bytes": usage,
            "quota_bytes": quota,
            "available_bytes": max(0, quota - usage),
            "usage_percent": round(usage / quota * 100, 2) if quota else 0,
        }
