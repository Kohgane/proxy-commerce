"""src/api/search_api.py — Phase 48: 검색 엔진 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

search_bp = Blueprint('search', __name__, url_prefix='/api/v1/search')


@search_bp.get('/status')
def search_status():
    return jsonify({'status': 'ok', 'module': 'search'})


@search_bp.get('/')
def search_products():
    """GET /api/v1/search/?q=<keyword>&sort=<sort>&limit=<n>."""
    from ..search.search_engine import SearchEngine
    from ..search.sort import SearchSorter
    from ..search.search_analytics import SearchAnalytics
    query = request.args.get('q', '')
    sort_by = request.args.get('sort', 'newest')
    limit = int(request.args.get('limit', 20))
    try:
        engine = SearchEngine()
        analytics = SearchAnalytics()
        results = engine.search(query, limit=limit)
        analytics.record_search(query, len(results))
        if sort_by != 'newest':
            sorter = SearchSorter()
            try:
                results = sorter.sort(results, sort_by)
            except ValueError:
                pass
        return jsonify({'query': query, 'count': len(results), 'results': results})
    except Exception as exc:
        logger.error("검색 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@search_bp.get('/autocomplete')
def autocomplete():
    """GET /api/v1/search/autocomplete?prefix=<prefix>."""
    from ..search.autocomplete import Autocomplete
    prefix = request.args.get('prefix', '')
    try:
        ac = Autocomplete()
        suggestions = ac.complete(prefix)
        return jsonify({'prefix': prefix, 'suggestions': suggestions})
    except Exception as exc:
        logger.error("자동완성 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@search_bp.get('/popular')
def popular_searches():
    """GET /api/v1/search/popular — 인기 검색어."""
    from ..search.search_analytics import SearchAnalytics
    try:
        analytics = SearchAnalytics()
        return jsonify(analytics.get_popular_queries())
    except Exception as exc:
        logger.error("인기 검색어 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
