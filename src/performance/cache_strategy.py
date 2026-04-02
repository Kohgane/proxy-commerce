import time
import threading


class CacheStrategy:
    def __init__(self, backend=None):
        self._store = {}  # key -> value
        self._ttls = {}   # key -> expiry timestamp (or None)
        self._tags = {}   # tag -> set of keys
        self._lock = threading.Lock()
        self._backend = backend  # optional Redis-like backend

    def _is_expired(self, key):
        expiry = self._ttls.get(key)
        return expiry is not None and time.time() > expiry

    def get(self, key):
        with self._lock:
            if key not in self._store or self._is_expired(key):
                if key in self._store:
                    del self._store[key]
                    self._ttls.pop(key, None)
                return None
            return self._store[key]

    def set(self, key, value, ttl=None, tags=None):
        with self._lock:
            self._store[key] = value
            self._ttls[key] = time.time() + ttl if ttl is not None else None
            if tags:
                for tag in tags:
                    self._tags.setdefault(tag, set()).add(key)

    def delete(self, key):
        with self._lock:
            self._store.pop(key, None)
            self._ttls.pop(key, None)

    def invalidate_by_tag(self, tag):
        with self._lock:
            keys = self._tags.pop(tag, set())
            for key in keys:
                self._store.pop(key, None)
                self._ttls.pop(key, None)

    def write_through(self, key, value, store_fn, ttl=None, tags=None):
        """Write to both cache and backing store atomically."""
        store_fn(key, value)
        self.set(key, value, ttl=ttl, tags=tags)

    def write_behind(self, key, value, store_fn, ttl=None, tags=None):
        """Write to cache first, then schedule backing store write."""
        self.set(key, value, ttl=ttl, tags=tags)
        t = threading.Thread(target=store_fn, args=(key, value), daemon=True)
        t.start()

    def cache_aside(self, key, load_fn, ttl=None, tags=None):
        """Load from cache; on miss, call load_fn and populate cache."""
        value = self.get(key)
        if value is None:
            value = load_fn(key)
            if value is not None:
                self.set(key, value, ttl=ttl, tags=tags)
        return value
