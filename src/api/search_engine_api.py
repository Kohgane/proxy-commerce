"""src/api/search_engine_api.py — 검색 엔진 고급 API Blueprint (Phase 57)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

search_engine_bp = Blueprint("search_engine", __name__, url_prefix="/api/v1/search/engine")

_index = None
_suggester = None
_facets = None
_ranker = None
_tokenizer = None


def _get_services():
    global _index, _suggester, _facets, _ranker, _tokenizer
    if _index is None:
        from ..search.search_index import SearchIndex
        from ..search.search_suggester import SearchSuggester
        from ..search.facet_collector import FacetCollector
        from ..search.ranker import Ranker
        from ..search.tokenizer import Tokenizer
        _index = SearchIndex()
        _suggester = SearchSuggester()
        _facets = FacetCollector()
        _ranker = Ranker()
        _tokenizer = Tokenizer()
    return _index, _suggester, _facets, _ranker, _tokenizer


@search_engine_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "search_engine"})


@search_engine_bp.post("/query")
def query():
    index, _, facets, ranker, tokenizer = _get_services()
    data = request.get_json(force=True) or {}
    q = data.get("q", "")
    top_k = int(data.get("top_k", 10))

    if not q:
        return jsonify({"error": "검색어 필요"}), 400

    results = index.search(q, top_k=top_k)
    doc_ids = [doc_id for doc_id, _ in results]
    docs = [{"doc_id": doc_id, "score": score, "fields": index.get_document(doc_id)}
            for doc_id, score in results]
    facet_data = facets.collect(doc_ids)
    return jsonify({"results": docs, "facets": facet_data, "total": len(docs)})


@search_engine_bp.post("/index")
def add_to_index():
    index, suggester, facets, _, tokenizer = _get_services()
    data = request.get_json(force=True) or {}
    doc_id = data.get("doc_id", "")
    fields = data.get("fields", {})
    facet_fields = data.get("facets", {})
    if not doc_id:
        return jsonify({"error": "doc_id 필요"}), 400
    index.add_document(doc_id, fields)
    if facet_fields:
        facets.add_document(doc_id, facet_fields)
    for term in fields.values():
        if isinstance(term, str):
            suggester.add_term(term)
    return jsonify({"indexed": doc_id}), 201


@search_engine_bp.get("/suggest")
def suggest():
    _, suggester, _, _, _ = _get_services()
    prefix = request.args.get("prefix", "")
    limit = request.args.get("limit", 5, type=int)
    suggestions = suggester.suggest(prefix, limit=limit)
    return jsonify({"suggestions": suggestions})


@search_engine_bp.get("/facets")
def get_facets():
    _, _, facets, _, _ = _get_services()
    field = request.args.get("field", "")
    if not field:
        return jsonify({"error": "field 파라미터 필요"}), 400
    return jsonify({"field": field, "facets": facets.get_facets(field)})


@search_engine_bp.get("/analytics")
def get_analytics():
    return jsonify({"info": "Phase 48 SearchAnalytics를 사용하세요."})
