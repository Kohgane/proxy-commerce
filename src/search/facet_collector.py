"""src/search/facet_collector.py — 패싯 집계기."""
from __future__ import annotations

from typing import Dict, List


class FacetCollector:
    """패싯(facet) 집계 관리."""

    def __init__(self) -> None:
        self._doc_facets: Dict[str, dict] = {}  # doc_id -> facets_dict

    def add_document(self, doc_id: str, facets_dict: dict) -> None:
        self._doc_facets[doc_id] = facets_dict

    def collect(self, doc_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """doc_ids에 대한 패싯 집계 결과 반환."""
        result: Dict[str, Dict[str, int]] = {}
        for doc_id in doc_ids:
            facets = self._doc_facets.get(doc_id, {})
            for field, value in facets.items():
                if field not in result:
                    result[field] = {}
                key = str(value)
                result[field][key] = result[field].get(key, 0) + 1
        return result

    def get_facets(self, field: str) -> Dict[str, int]:
        """특정 필드의 전체 패싯 집계."""
        counts: Dict[str, int] = {}
        for facets in self._doc_facets.values():
            if field in facets:
                key = str(facets[field])
                counts[key] = counts.get(key, 0) + 1
        return counts
