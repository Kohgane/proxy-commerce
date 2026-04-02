"""src/auth/rate_limiter.py — Token bucket rate limiter for auth/API key usage."""

import time


class TokenBucketRateLimiter:
    """Token bucket rate limiter. Stores per-key state in memory."""

    def __init__(self, capacity: int = 10, refill_rate: float = 1.0):
        """
        Args:
            capacity: Maximum number of tokens in the bucket.
            refill_rate: Tokens added per second.
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets: dict = {}  # key -> {"tokens": float, "last_refill": float}

    def _get_bucket(self, key: str) -> dict:
        if key not in self._buckets:
            self._buckets[key] = {'tokens': float(self.capacity), 'last_refill': time.time()}
        return self._buckets[key]

    def _refill(self, bucket: dict) -> None:
        now = time.time()
        elapsed = now - bucket['last_refill']
        added = elapsed * self.refill_rate
        bucket['tokens'] = min(self.capacity, bucket['tokens'] + added)
        bucket['last_refill'] = now

    def consume(self, key: str, tokens: int = 1) -> bool:
        """Consume tokens. Returns True if allowed, False if rate limited."""
        bucket = self._get_bucket(key)
        self._refill(bucket)
        if bucket['tokens'] >= tokens:
            bucket['tokens'] -= tokens
            return True
        return False

    def get_remaining(self, key: str) -> float:
        """Return the current token count for a key."""
        bucket = self._get_bucket(key)
        self._refill(bucket)
        return bucket['tokens']

    def reset(self, key: str) -> None:
        """Reset the bucket for a key to full capacity."""
        self._buckets[key] = {'tokens': float(self.capacity), 'last_refill': time.time()}
