"""src/bundles/availability.py — Phase 44: 번들 재고 확인."""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class BundleAvailability:
    """번들 재고 확인.

    - 모든 구성 상품 재고가 있어야 번들 가용
    - 부분 가용 시 대안 제안
    """

    def check(
        self,
        bundle: dict,
        stock_catalog: Dict[str, int],
    ) -> dict:
        """번들 가용 여부 확인.

        Args:
            bundle:        번들 객체 (items 포함)
            stock_catalog: {product_id: stock_quantity}

        Returns:
            {available, unavailable_items, partial}
        """
        unavailable = []
        for item in bundle.get('items', []):
            pid = item['product_id']
            required = item.get('quantity', 1)
            in_stock = stock_catalog.get(pid, 0)
            if in_stock < required:
                unavailable.append({
                    'product_id': pid,
                    'required': required,
                    'in_stock': in_stock,
                })
        available = len(unavailable) == 0
        partial = 0 < len(unavailable) < len(bundle.get('items', [1]))
        return {
            'available': available,
            'unavailable_items': unavailable,
            'partial': partial,
        }

    def suggest_alternatives(
        self,
        unavailable_items: List[dict],
        catalog: List[dict],
    ) -> List[dict]:
        """재고 없는 상품의 대안 상품 제안 (같은 카테고리)."""
        suggestions = []
        for item in unavailable_items:
            pid = item['product_id']
            src = next((p for p in catalog if p.get('id') == pid), None)
            if src is None:
                continue
            category = src.get('category', '')
            alternatives = [
                p for p in catalog
                if p.get('id') != pid and p.get('category') == category
            ][:3]
            suggestions.append({
                'original_product_id': pid,
                'alternatives': alternatives,
            })
        return suggestions
