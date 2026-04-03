"""src/api/cache_api.py — 캐시 계층 API Blueprint (Phase 65)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

cache_bp = Blueprint("cache", __name__, url_prefix="/api/v1/cache")

_manager = None
_stats = None
_invalidator = None


def _get_services():
    global _manager, _stats, _invalidator
    if _manager is None:
        from ..cache_layer.cache_manager import CacheManager
        from ..cache_layer.cache_stats import CacheStats
        from ..cache_layer.cache_invalidator import CacheInvalidator
        _manager = CacheManager()
        _stats = CacheStats()
        _invalidator = CacheInvalidator(_manager)
    return _manager, _stats, _invalidator


@cache_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "cache"})


@cache_bp.get("/stats")
def get_stats():
    _, stats, _ = _get_services()
    return jsonify(stats.get_stats())


@cache_bp.post("/invalidate")
def invalidate():
    _, _, invalidator = _get_services()
    data = request.get_json(force=True) or {}
    pattern = data.get("pattern")
    tags = data.get("tags", [])
    count = 0
    if pattern:
        count += invalidator.invalidate_by_pattern(pattern)
    for tag in tags:
        count += invalidator.invalidate_by_tag(tag)
    return jsonify({"invalidated": count})


@cache_bp.post("/warm")
def warm_cache():
    manager, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    keys = data.get("keys", [])
    from ..cache_layer.cache_warmer import CacheWarmer
    warmer = CacheWarmer(manager)
    results = warmer.warm(lambda k: f"warmed:{k}", keys)
    return jsonify(results)


@cache_bp.get("/keys")
def list_keys():
    manager, _, _ = _get_services()
    return jsonify({"keys": manager.keys()})
