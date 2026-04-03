"""src/search/sort.py — Phase 48: 정렬."""
import logging
from typing import List

logger = logging.getLogger(__name__)

SORT_FIELDS = {'price_asc', 'price_desc', 'newest', 'popularity', 'rating'}


class SearchSorter:
    """검색 결과 정렬.

    정렬: price_asc, price_desc, newest, popularity, rating
    """

    def sort(self, products: List[dict], sort_by: str = 'newest') -> List[dict]:
        """상품 목록 정렬."""
        if sort_by not in SORT_FIELDS:
            raise ValueError(f"지원하지 않는 정렬: {sort_by}. 사용 가능: {SORT_FIELDS}")
        result = list(products)
        if sort_by == 'price_asc':
            result.sort(key=lambda p: float(p.get('price', 0)))
        elif sort_by == 'price_desc':
            result.sort(key=lambda p: float(p.get('price', 0)), reverse=True)
        elif sort_by == 'newest':
            result.sort(key=lambda p: p.get('created_at', ''), reverse=True)
        elif sort_by == 'popularity':
            result.sort(key=lambda p: int(p.get('sales_count', 0)), reverse=True)
        elif sort_by == 'rating':
            result.sort(key=lambda p: float(p.get('rating', 0)), reverse=True)
        return result
