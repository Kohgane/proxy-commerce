"""src/wishlist/recommendations.py — Phase 43: 위시리스트 기반 추천."""
import logging
from collections import Counter
from typing import List, Optional

logger = logging.getLogger(__name__)


class WishlistRecommender:
    """위시리스트 아이템의 카테고리/태그 분석 → 유사 상품 추천.

    - 카탈로그는 외부에서 주입 (product dict: id, category, tags)
    - 위시리스트 아이템과 같은 카테고리/태그를 가진 상품 추천
    """

    def __init__(self, catalog: Optional[List[dict]] = None):
        self._catalog = catalog or []

    def set_catalog(self, catalog: List[dict]):
        self._catalog = catalog

    def recommend(self, wishlist_items: List[dict], limit: int = 10) -> List[dict]:
        """위시리스트 아이템 기반 추천 상품 목록.

        Args:
            wishlist_items: 위시리스트 아이템 목록 (product_id 포함)
            limit: 최대 추천 수
        """
        if not self._catalog or not wishlist_items:
            return []

        # 위시리스트에 담긴 product_id 집합
        liked_ids = {item['product_id'] for item in wishlist_items}

        # 좋아하는 상품의 카테고리/태그 집계
        category_count: Counter = Counter()
        tag_count: Counter = Counter()
        for product in self._catalog:
            if product.get('id') in liked_ids:
                cat = product.get('category', '')
                if cat:
                    category_count[cat] += 1
                for tag in product.get('tags', []):
                    tag_count[tag] += 1

        # 카탈로그에서 미담은 상품 스코어링
        scores = []
        for product in self._catalog:
            if product.get('id') in liked_ids:
                continue
            score = 0
            cat = product.get('category', '')
            score += category_count.get(cat, 0) * 3
            for tag in product.get('tags', []):
                score += tag_count.get(tag, 0) * 2
            if score > 0:
                scores.append((score, product))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scores[:limit]]

    def similar_products(self, product_id: str, limit: int = 5) -> List[dict]:
        """특정 상품과 유사한 상품 (같은 카테고리 + 태그 교집합)."""
        source = next((p for p in self._catalog if p.get('id') == product_id), None)
        if source is None:
            return []

        src_cat = source.get('category', '')
        src_tags = set(source.get('tags', []))

        scores = []
        for product in self._catalog:
            if product.get('id') == product_id:
                continue
            score = 0
            if product.get('category') == src_cat:
                score += 3
            tag_overlap = src_tags & set(product.get('tags', []))
            score += len(tag_overlap) * 2
            if score > 0:
                scores.append((score, product))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scores[:limit]]
