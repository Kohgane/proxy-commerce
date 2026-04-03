"""src/marketplace_sync/conflict_resolver.py — 동기화 충돌 해결기."""
from __future__ import annotations


class SyncConflictResolver:
    """동기화 충돌 해결기."""

    def resolve(self, local_data: dict, remote_data: dict, strategy: str = "marketplace_wins") -> dict:
        """충돌을 해결한다."""
        if strategy == "marketplace_wins":
            result = dict(local_data)
            result.update(remote_data)
            result["_resolved_by"] = "marketplace_wins"
            return result
        elif strategy == "local_wins":
            result = dict(remote_data)
            result.update(local_data)
            result["_resolved_by"] = "local_wins"
            return result
        elif strategy == "manual":
            return {
                "_conflict": True,
                "_resolved_by": "manual",
                "local": local_data,
                "remote": remote_data,
            }
        else:
            result = dict(local_data)
            result.update(remote_data)
            result["_resolved_by"] = strategy
            return result
