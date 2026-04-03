"""src/marketplace_sync/sync_manager.py — 마켓플레이스 동기화 관리자."""
from __future__ import annotations

from .adapter import CoupangSyncAdapter, NaverSyncAdapter, GmarketSyncAdapter
from .sync_job import SyncJob
from .sync_log import SyncLog


class MarketplaceSyncManager:
    """마켓플레이스 동기화 관리자."""

    def __init__(self) -> None:
        self._adapters = {
            "coupang": CoupangSyncAdapter(),
            "naver": NaverSyncAdapter(),
            "gmarket": GmarketSyncAdapter(),
        }
        self._log = SyncLog()
        self._jobs: list[SyncJob] = []

    def sync(self, marketplace: str, job_type: str = "all") -> SyncJob:
        """마켓플레이스를 동기화한다."""
        adapter = self._adapters.get(marketplace)
        job = SyncJob(marketplace=marketplace, job_type=job_type)
        job.start()

        if adapter is None:
            job.fail(f"알 수 없는 마켓플레이스: {marketplace}")
        else:
            try:
                synced = 0
                types = ["products", "orders", "inventory", "prices"] if job_type == "all" else [job_type]
                for t in types:
                    method = getattr(adapter, f"sync_{t}", None)
                    if method:
                        records = method()
                        synced += len(records)
                job.complete(synced=synced)
            except Exception as exc:
                job.fail(str(exc))

        self._jobs.append(job)
        self._log.record(job)
        return job

    def get_status(self) -> dict:
        """동기화 현황을 반환한다."""
        marketplaces = {}
        for marketplace in self._adapters:
            jobs = [j for j in self._jobs if j.marketplace == marketplace]
            last_job = jobs[-1] if jobs else None
            marketplaces[marketplace] = {
                "status": last_job.status if last_job else "never",
                "last_sync": last_job.completed_at.isoformat() if last_job and last_job.completed_at else None,
            }
        return {
            "marketplaces": marketplaces,
            "total_jobs": len(self._jobs),
        }

    def list_jobs(self, limit: int = 20) -> list:
        """최근 작업 목록을 반환한다."""
        return [j.to_dict() for j in self._jobs[-limit:]]
