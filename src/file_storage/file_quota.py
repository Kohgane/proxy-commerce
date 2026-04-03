"""src/file_storage/file_quota.py — 스토리지 사용량 관리."""
from __future__ import annotations

from typing import Dict, Optional


class FileQuota:
    """사용자별/테넌트별 스토리지 사용량 관리."""

    DEFAULT_QUOTA_BYTES = 1 * 1024 * 1024 * 1024  # 1GB

    def __init__(self) -> None:
        self._usage: Dict[str, int] = {}      # owner_id -> bytes
        self._quotas: Dict[str, int] = {}     # owner_id -> max bytes

    def set_quota(self, owner_id: str, max_bytes: int) -> None:
        self._quotas[owner_id] = max_bytes

    def get_quota(self, owner_id: str) -> int:
        return self._quotas.get(owner_id, self.DEFAULT_QUOTA_BYTES)

    def get_usage(self, owner_id: str) -> int:
        return self._usage.get(owner_id, 0)

    def add_usage(self, owner_id: str, size_bytes: int) -> None:
        self._usage[owner_id] = self._usage.get(owner_id, 0) + size_bytes

    def subtract_usage(self, owner_id: str, size_bytes: int) -> None:
        current = self._usage.get(owner_id, 0)
        self._usage[owner_id] = max(0, current - size_bytes)

    def check_quota(self, owner_id: str, size_bytes: int) -> bool:
        """사용 가능 여부 확인 (True: 사용 가능)."""
        quota = self.get_quota(owner_id)
        usage = self.get_usage(owner_id)
        return (usage + size_bytes) <= quota

    def get_summary(self, owner_id: str) -> dict:
        quota = self.get_quota(owner_id)
        usage = self.get_usage(owner_id)
        return {
            "owner_id": owner_id,
            "quota_bytes": quota,
            "used_bytes": usage,
            "available_bytes": max(0, quota - usage),
            "usage_pct": round(usage / quota * 100, 2) if quota > 0 else 0.0,
        }

    def list_all(self) -> list:
        all_owners = set(self._usage.keys()) | set(self._quotas.keys())
        return [self.get_summary(o) for o in sorted(all_owners)]
