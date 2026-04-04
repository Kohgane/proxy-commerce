"""src/mobile_api/mobile_product.py — 모바일 상품 서비스."""
from __future__ import annotations

import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MobileProductService:
    """모바일 상품 서비스 — 커서 기반 페이지네이션."""

    def __init__(self):
        self._products: list[dict] = []
        self._populate_sample()

    def _populate_sample(self):
        sample = [
            {'sku': 'P001', 'name': 'Wireless Headphones', 'price': 99.99, 'currency': 'USD',
             'category': 'electronics', 'images': ['https://cdn.example.com/p001.jpg'], 'stock': 50,
             'description': 'Premium wireless headphones', 'locale': 'en', 'rating': 4.5},
            {'sku': 'P002', 'name': '블루투스 이어폰', 'price': 49000, 'currency': 'KRW',
             'category': 'electronics', 'images': ['https://cdn.example.com/p002.jpg'], 'stock': 30,
             'description': '고품질 블루투스 이어폰', 'locale': 'ko', 'rating': 4.2},
            {'sku': 'P003', 'name': 'Running Shoes', 'price': 129.99, 'currency': 'USD',
             'category': 'sports', 'images': ['https://cdn.example.com/p003.jpg'], 'stock': 20,
             'description': 'Lightweight running shoes', 'locale': 'en', 'rating': 4.7},
            {'sku': 'P004', 'name': '스마트 워치', 'price': 299000, 'currency': 'KRW',
             'category': 'electronics', 'images': ['https://cdn.example.com/p004.jpg'], 'stock': 15,
             'description': '건강 모니터링 스마트워치', 'locale': 'ko', 'rating': 4.3},
            {'sku': 'P005', 'name': 'Coffee Maker', 'price': 79.99, 'currency': 'USD',
             'category': 'kitchen', 'images': ['https://cdn.example.com/p005.jpg'], 'stock': 40,
             'description': 'Automatic drip coffee maker', 'locale': 'en', 'rating': 4.1},
            {'sku': 'P006', 'name': '노트북 가방', 'price': 45000, 'currency': 'KRW',
             'category': 'accessories', 'images': ['https://cdn.example.com/p006.jpg'], 'stock': 25,
             'description': '방수 노트북 가방 15인치', 'locale': 'ko', 'rating': 4.4},
        ]
        self._products = sample

    def list_products(self, cursor: Optional[str] = None, limit: int = 20,
                      category: Optional[str] = None, search: Optional[str] = None) -> dict:
        items = list(self._products)
        if category:
            items = [p for p in items if p['category'] == category]
        if search:
            s = search.lower()
            items = [p for p in items if s in p['name'].lower() or s in p.get('description', '').lower()]

        offset = 0
        if cursor:
            try:
                offset = int(base64.b64decode(cursor.encode()).decode())
            except Exception:
                offset = 0

        page = items[offset:offset + limit]
        has_more = offset + limit < len(items)
        next_cursor = None
        if has_more:
            next_cursor = base64.b64encode(str(offset + limit).encode()).decode()

        return {'items': page, 'next_cursor': next_cursor, 'has_more': has_more, 'total': len(items)}

    def get_product(self, sku: str) -> Optional[dict]:
        for p in self._products:
            if p['sku'] == sku:
                return p
        return None

    def get_recommended(self, user_id: str, top_n: int = 10) -> list[dict]:
        try:
            from ..ai_recommendation import AIRecommendationEngine
            engine = AIRecommendationEngine()
            results = engine.get_recommendations(user_id, top_n=top_n)
            skus = [r.product_id for r in results]
            recs = [self.get_product(s) for s in skus if self.get_product(s)]
            if recs:
                return recs
        except Exception as exc:
            logger.debug("AI recommendation fallback: %s", exc)
        return self._products[:top_n]

    def get_trending(self, category: Optional[str] = None, top_n: int = 10) -> list[dict]:
        items = self._products
        if category:
            items = [p for p in items if p['category'] == category]
        sorted_items = sorted(items, key=lambda p: p.get('rating', 0), reverse=True)
        return sorted_items[:top_n]

    def get_categories(self) -> list[dict]:
        cats: dict[str, int] = {}
        for p in self._products:
            cats[p['category']] = cats.get(p['category'], 0) + 1
        return [{'name': name, 'count': count, 'children': []} for name, count in cats.items()]
