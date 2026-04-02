import threading
import queue


class ConnectionPool:
    def __init__(self, name, factory_fn, pool_size=5):
        self.name = name
        self._factory_fn = factory_fn
        self._pool_size = pool_size
        self._pool = queue.Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._created = 0
        self._checked_out = 0

        for _ in range(pool_size):
            conn = factory_fn()
            self._pool.put(conn)
            self._created += 1

    def acquire(self, timeout=5):
        conn = self._pool.get(timeout=timeout)
        with self._lock:
            self._checked_out += 1
        return conn

    def release(self, conn):
        self._pool.put(conn)
        with self._lock:
            self._checked_out = max(0, self._checked_out - 1)

    def stats(self):
        return {
            "name": self.name,
            "pool_size": self._pool_size,
            "available": self._pool.qsize(),
            "checked_out": self._checked_out,
            "created": self._created,
        }


class ConnectionPoolManager:
    def __init__(self):
        self._pools = {}
        self._lock = threading.Lock()

    def get_pool(self, name, factory_fn, pool_size=5):
        with self._lock:
            if name not in self._pools:
                self._pools[name] = ConnectionPool(name, factory_fn, pool_size)
            return self._pools[name]

    def health_check(self, name):
        with self._lock:
            pool = self._pools.get(name)
        if pool is None:
            return False
        return pool.stats()["available"] > 0

    def get_stats(self):
        with self._lock:
            pools = dict(self._pools)
        return {name: pool.stats() for name, pool in pools.items()}
