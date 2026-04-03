"""tests/test_marketplace_sync.py — Phase 71 마켓플레이스 동기화 테스트."""
from __future__ import annotations

import pytest
from src.marketplace_sync.adapter import CoupangSyncAdapter, NaverSyncAdapter, GmarketSyncAdapter
from src.marketplace_sync.sync_job import SyncJob
from src.marketplace_sync.conflict_resolver import SyncConflictResolver
from src.marketplace_sync.sync_scheduler import SyncScheduler
from src.marketplace_sync.sync_log import SyncLog
from src.marketplace_sync.sync_manager import MarketplaceSyncManager


class TestAdapter:
    def test_coupang_sync_products(self):
        adapter = CoupangSyncAdapter()
        products = adapter.sync_products()
        assert isinstance(products, list)
        assert len(products) > 0

    def test_coupang_sync_orders(self):
        adapter = CoupangSyncAdapter()
        orders = adapter.sync_orders()
        assert all("order_id" in o for o in orders)

    def test_naver_sync_inventory(self):
        adapter = NaverSyncAdapter()
        inventory = adapter.sync_inventory()
        assert isinstance(inventory, list)

    def test_gmarket_sync_prices(self):
        adapter = GmarketSyncAdapter()
        prices = adapter.sync_prices()
        assert all("price" in p for p in prices)


class TestSyncJob:
    def test_initial_state(self):
        job = SyncJob(marketplace="coupang", job_type="products")
        assert job.status == "pending"
        assert job.records_synced == 0

    def test_start(self):
        job = SyncJob(marketplace="coupang", job_type="products")
        job.start()
        assert job.status == "running"
        assert job.started_at is not None

    def test_complete(self):
        job = SyncJob(marketplace="coupang", job_type="products")
        job.start()
        job.complete(synced=10, failed=2)
        assert job.status == "completed"
        assert job.records_synced == 10
        assert job.records_failed == 2

    def test_fail(self):
        job = SyncJob(marketplace="coupang", job_type="products")
        job.start()
        job.fail("연결 오류")
        assert job.status == "failed"
        assert job.error_message == "연결 오류"

    def test_to_dict(self):
        job = SyncJob(marketplace="naver", job_type="orders")
        d = job.to_dict()
        assert d["marketplace"] == "naver"
        assert "job_id" in d


class TestSyncConflictResolver:
    def test_marketplace_wins(self):
        resolver = SyncConflictResolver()
        local = {"price": 1000, "stock": 5}
        remote = {"price": 1500, "marketplace_id": "cp-001"}
        result = resolver.resolve(local, remote, strategy="marketplace_wins")
        assert result["price"] == 1500
        assert result["_resolved_by"] == "marketplace_wins"

    def test_local_wins(self):
        resolver = SyncConflictResolver()
        local = {"price": 1000}
        remote = {"price": 1500}
        result = resolver.resolve(local, remote, strategy="local_wins")
        assert result["price"] == 1000

    def test_manual_strategy(self):
        resolver = SyncConflictResolver()
        result = resolver.resolve({"a": 1}, {"b": 2}, strategy="manual")
        assert result["_conflict"] is True
        assert "local" in result
        assert "remote" in result


class TestSyncScheduler:
    def test_schedule(self):
        scheduler = SyncScheduler()
        result = scheduler.schedule("coupang", interval_minutes=30)
        assert result["marketplace"] == "coupang"
        assert result["interval_minutes"] == 30

    def test_get_schedule(self):
        scheduler = SyncScheduler()
        scheduler.schedule("naver", 60)
        s = scheduler.get_schedule("naver")
        assert s["marketplace"] == "naver"

    def test_get_schedule_nonexistent(self):
        scheduler = SyncScheduler()
        assert scheduler.get_schedule("unknown") == {}

    def test_list_schedules(self):
        scheduler = SyncScheduler()
        scheduler.schedule("coupang", 60)
        scheduler.schedule("naver", 30)
        assert len(scheduler.list_schedules()) == 2

    def test_should_sync_no_schedule(self):
        scheduler = SyncScheduler()
        assert scheduler.should_sync("coupang") is False


class TestSyncLog:
    def test_record(self):
        log = SyncLog()
        job = SyncJob(marketplace="coupang", job_type="products")
        job.start()
        job.complete(synced=5)
        log.record(job)
        logs = log.get_logs()
        assert len(logs) == 1

    def test_get_logs_filter_marketplace(self):
        log = SyncLog()
        job1 = SyncJob(marketplace="coupang", job_type="products")
        job1.complete()
        job2 = SyncJob(marketplace="naver", job_type="orders")
        job2.complete()
        log.record(job1)
        log.record(job2)
        coupang_logs = log.get_logs(marketplace="coupang")
        assert all(l["marketplace"] == "coupang" for l in coupang_logs)

    def test_get_summary(self):
        log = SyncLog()
        job1 = SyncJob(marketplace="coupang", job_type="products")
        job1.complete()
        job2 = SyncJob(marketplace="naver", job_type="orders")
        job2.fail("error")
        log.record(job1)
        log.record(job2)
        summary = log.get_summary()
        assert summary["total_jobs"] == 2
        assert summary["success_count"] == 1
        assert summary["failure_count"] == 1


class TestMarketplaceSyncManager:
    def test_sync_coupang(self):
        mgr = MarketplaceSyncManager()
        job = mgr.sync("coupang")
        assert job.marketplace == "coupang"
        assert job.status == "completed"

    def test_sync_unknown_marketplace(self):
        mgr = MarketplaceSyncManager()
        job = mgr.sync("unknown_market")
        assert job.status == "failed"

    def test_get_status(self):
        mgr = MarketplaceSyncManager()
        mgr.sync("coupang")
        status = mgr.get_status()
        assert "marketplaces" in status

    def test_list_jobs(self):
        mgr = MarketplaceSyncManager()
        mgr.sync("coupang")
        mgr.sync("naver")
        jobs = mgr.list_jobs()
        assert len(jobs) == 2
