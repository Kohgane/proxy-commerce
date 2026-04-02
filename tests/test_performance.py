import time
import threading
import pytest

from src.performance.cache_strategy import CacheStrategy
from src.performance.query_optimizer import QueryOptimizer
from src.performance.async_tasks import AsyncTaskQueue
from src.performance.connection_pool import ConnectionPoolManager


# ---------------------------------------------------------------------------
# CacheStrategy tests
# ---------------------------------------------------------------------------

def test_cache_strategy_set_get():
    cache = CacheStrategy()
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"
    assert cache.get("missing") is None


def test_cache_strategy_ttl_expiry():
    cache = CacheStrategy()
    cache.set("k2", "v2", ttl=0.05)  # 50 ms
    assert cache.get("k2") == "v2"
    time.sleep(0.1)
    assert cache.get("k2") is None


def test_cache_strategy_write_through():
    cache = CacheStrategy()
    persisted = {}

    def store_fn(key, value):
        persisted[key] = value

    cache.write_through("wt_key", "wt_val", store_fn)
    assert cache.get("wt_key") == "wt_val"
    assert persisted["wt_key"] == "wt_val"


def test_cache_strategy_cache_aside():
    cache = CacheStrategy()
    db = {"db_key": "db_val"}

    def load_fn(key):
        return db.get(key)

    # First call: cache miss → loads from db
    result = cache.cache_aside("db_key", load_fn)
    assert result == "db_val"
    # Second call: cache hit
    db["db_key"] = "changed"
    result2 = cache.cache_aside("db_key", load_fn)
    assert result2 == "db_val"  # still cached


def test_cache_strategy_invalidate_by_tag():
    cache = CacheStrategy()
    cache.set("a", 1, tags=["group1"])
    cache.set("b", 2, tags=["group1"])
    cache.set("c", 3, tags=["group2"])

    cache.invalidate_by_tag("group1")
    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.get("c") == 3


# ---------------------------------------------------------------------------
# QueryOptimizer tests
# ---------------------------------------------------------------------------

def test_query_optimizer_batch_get():
    opt = QueryOptimizer()
    db = {1: "one", 2: "two", 3: "three"}

    def fetch_fn(keys):
        return {k: db[k] for k in keys if k in db}

    result = opt.batch_get([1, 2, 3], fetch_fn)
    assert result == {1: "one", 2: "two", 3: "three"}


def test_query_optimizer_prefetch_related():
    opt = QueryOptimizer()
    items = [{"id": 1}, {"id": 2}, {"id": 3}]
    related_db = {1: "rel_1", 2: "rel_2", 3: "rel_3"}

    def relation_fn(ids):
        return {i: related_db[i] for i in ids if i in related_db}

    result = opt.prefetch_related(items, relation_fn, key_fn=lambda x: x["id"])
    assert result == {1: "rel_1", 2: "rel_2", 3: "rel_3"}


# ---------------------------------------------------------------------------
# AsyncTaskQueue tests
# ---------------------------------------------------------------------------

def _wait_for_status(queue, task_id, target_statuses, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = queue.get_status(task_id)
        if status in target_statuses:
            return status
        time.sleep(0.05)
    return queue.get_status(task_id)


def test_async_task_queue_enqueue_and_result():
    q = AsyncTaskQueue(base_delay=0.01)

    def add(a, b):
        return a + b

    task_id = q.enqueue(add, 3, 4)
    assert isinstance(task_id, str)

    status = _wait_for_status(q, task_id, {"done", "failed"})
    assert status == "done"
    result = q.get_result(task_id)
    assert result["result"] == 7
    assert result["error"] is None


def test_async_task_queue_retry():
    q = AsyncTaskQueue(base_delay=0.01)
    call_count = {"n": 0}

    def flaky():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise ValueError("transient error")
        return "ok"

    task_id = q.enqueue_retryable(flaky)
    status = _wait_for_status(q, task_id, {"done", "failed"}, timeout=10.0)
    assert status == "done"
    result = q.get_result(task_id)
    assert result["result"] == "ok"
    assert result["attempts"] == 3


# ---------------------------------------------------------------------------
# ConnectionPool tests
# ---------------------------------------------------------------------------

def test_connection_pool_basic():
    manager = ConnectionPoolManager()
    conn_id = {"n": 0}

    def factory():
        conn_id["n"] += 1
        return {"conn_id": conn_id["n"]}

    pool = manager.get_pool("test_pool", factory, pool_size=3)
    conn = pool.acquire()
    assert "conn_id" in conn
    pool.release(conn)

    stats = pool.stats()
    assert stats["pool_size"] == 3
    assert stats["available"] == 3


def test_connection_pool_health_check():
    manager = ConnectionPoolManager()

    def factory():
        return object()

    manager.get_pool("hp", factory, pool_size=2)
    assert manager.health_check("hp") is True
    assert manager.health_check("nonexistent") is False

    all_stats = manager.get_stats()
    assert "hp" in all_stats
    assert all_stats["hp"]["pool_size"] == 2
