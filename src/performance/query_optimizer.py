class QueryOptimizer:
    def batch_get(self, keys, fetch_fn):
        """Bulk-fetch items to avoid N+1 queries.

        fetch_fn(keys) must return a dict mapping key -> value.
        """
        if not keys:
            return {}
        return fetch_fn(list(keys))

    def prefetch_related(self, items, relation_fn, key_fn):
        """Prefetch related objects for a list of items.

        relation_fn(ids) -> dict mapping id -> related object
        key_fn(item)     -> the id used to look up each item's relation

        Returns a dict mapping id -> related object.
        """
        if not items:
            return {}
        ids = [key_fn(item) for item in items]
        return relation_fn(ids)
