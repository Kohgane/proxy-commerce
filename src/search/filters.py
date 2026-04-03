"""src/search/filters.py — Phase 48: 필터 시스템."""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class SearchFilter:
    """검색 결과 필터링 (AND 로직).

    필터: 가격 범위, 카테고리, 마켓플레이스, 평점, 재고 있음
    """

    def filter(
        self,
        products: List[dict],
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        categories: Optional[List[str]] = None,
        marketplaces: Optional[List[str]] = None,
        min_rating: Optional[float] = None,
        in_stock_only: bool = False,
    ) -> List[dict]:
        """상품 목록 필터링."""
        result = []
        for product in products:
            if not self._match(product, min_price, max_price, categories,
                               marketplaces, min_rating, in_stock_only):
                continue
            result.append(product)
        return result

    def _match(
        self,
        product: dict,
        min_price: Optional[float],
        max_price: Optional[float],
        categories: Optional[List[str]],
        marketplaces: Optional[List[str]],
        min_rating: Optional[float],
        in_stock_only: bool,
    ) -> bool:
        price = float(product.get('price', 0))
        if min_price is not None and price < min_price:
            return False
        if max_price is not None and price > max_price:
            return False
        if categories:
            if product.get('category') not in categories:
                return False
        if marketplaces:
            if product.get('marketplace') not in marketplaces:
                return False
        if min_rating is not None:
            rating = float(product.get('rating', 0))
            if rating < min_rating:
                return False
        if in_stock_only:
            if int(product.get('stock', 0)) <= 0:
                return False
        return True
