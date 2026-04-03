"""src/recommendation/content_based_filter.py — 콘텐츠 기반 필터링."""
from __future__ import annotations


class ContentBasedFilter:
    """콘텐츠 기반 필터링 추천기."""

    def __init__(self) -> None:
        self._products: dict[str, dict] = {}

    def add_product(self, product_id: str, category: str, tags: list, price: float, **kwargs) -> None:
        """상품을 추가한다."""
        self._products[product_id] = {
            'product_id': product_id,
            'category': category,
            'tags': set(tags),
            'price': price,
            **kwargs,
        }

    def similar(self, product_id: str, top_n: int = 10) -> list:
        """유사한 상품 목록을 반환한다."""
        target = self._products.get(product_id)
        if target is None:
            return []
        results = []
        for pid, prod in self._products.items():
            if pid == product_id:
                continue
            score = 0.0
            if prod['category'] == target['category']:
                score += 1.0
            common_tags = prod['tags'] & target['tags']
            score += len(common_tags) * 0.5
            results.append({'product_id': pid, 'score': score})
        return sorted(results, key=lambda x: -x['score'])[:top_n]
