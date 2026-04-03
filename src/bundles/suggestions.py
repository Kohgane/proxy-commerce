"""src/bundles/suggestions.py — Phase 44: 번들 제안 (구매 이력 기반)."""
import logging
from collections import Counter
from itertools import combinations
from typing import List

logger = logging.getLogger(__name__)


class BundleSuggestion:
    """구매 이력 기반 함께 구매 빈도 분석 → 번들 제안.

    구매 이력: [{order_id, items: [product_id]}]
    """

    def __init__(self):
        self._pair_counts: Counter = Counter()
        self._orders_processed = 0

    def process_orders(self, orders: List[dict]):
        """주문 이력으로 공동 구매 빈도 집계."""
        for order in orders:
            items = list(set(order.get('items', [])))
            for pair in combinations(sorted(items), 2):
                self._pair_counts[pair] += 1
        self._orders_processed += len(orders)

    def suggest_bundles(self, min_frequency: int = 2, top_n: int = 10) -> List[dict]:
        """빈도 높은 상품 쌍 → 번들 제안 목록."""
        results = []
        for pair, count in self._pair_counts.most_common(top_n * 3):
            if count < min_frequency:
                break
            results.append({
                'product_ids': list(pair),
                'frequency': count,
                'suggestion_score': count / max(self._orders_processed, 1),
            })
        return results[:top_n]

    def suggest_for_product(self, product_id: str, top_n: int = 5) -> List[dict]:
        """특정 상품과 함께 구매되는 상품 제안."""
        related: Counter = Counter()
        for (a, b), count in self._pair_counts.items():
            if a == product_id:
                related[b] += count
            elif b == product_id:
                related[a] += count
        return [
            {'product_id': pid, 'frequency': cnt}
            for pid, cnt in related.most_common(top_n)
        ]
