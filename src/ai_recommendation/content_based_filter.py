"""src/ai_recommendation/content_based_filter.py — Phase 94: 고도화 콘텐츠 기반 필터링."""
from __future__ import annotations

import math
from collections import defaultdict

from .recommendation_model import PriceTier, ProductVector, RecommendationResult

# 속성별 가중치
_ATTR_WEIGHT = {
    "category": 3.0,
    "brand": 2.0,
    "price_tier": 1.5,
    "tags": 1.0,
    "origin_country": 0.5,
}


def _price_to_tier(price: float) -> PriceTier:
    if price < 10_000:
        return PriceTier.LOW
    if price < 50_000:
        return PriceTier.MID
    if price < 200_000:
        return PriceTier.HIGH
    return PriceTier.PREMIUM


class AdvancedContentBasedFilter:
    """고도화 콘텐츠 기반 필터링.

    - 상품 속성 벡터화 (카테고리, 브랜드, 가격대, 태그, 원산지)
    - TF-IDF 기반 상품 설명 유사도
    - 가중 속성 매칭 (카테고리 3x, 브랜드 2x, 가격대 1.5x, 태그 1x)
    """

    def __init__(self) -> None:
        self._products: dict[str, ProductVector] = {}
        # TF-IDF용 역인덱스: term -> {product_id: tf}
        self._term_index: dict[str, dict[str, float]] = defaultdict(dict)
        self._doc_count = 0

    def add_product(self, product: ProductVector) -> None:
        """상품을 추가하고 TF-IDF 인덱스를 업데이트한다."""
        self._products[product.product_id] = product
        self._doc_count += 1
        if product.description:
            self._index_description(product.product_id, product.description)

    def add_product_dict(
        self,
        product_id: str,
        category: str,
        brand: str = "",
        price: float = 0.0,
        tags: list[str] | None = None,
        description: str = "",
        origin_country: str = "",
        popularity_score: float = 0.0,
    ) -> None:
        """딕셔너리 파라미터로 상품을 추가한다."""
        pv = ProductVector(
            product_id=product_id,
            category=category,
            brand=brand,
            price_tier=_price_to_tier(price),
            tags=tags or [],
            description=description,
            origin_country=origin_country,
            popularity_score=popularity_score,
        )
        self.add_product(pv)

    def _index_description(self, product_id: str, description: str) -> None:
        """상품 설명을 TF-IDF 역인덱스에 추가한다."""
        tokens = description.lower().split()
        total = len(tokens)
        if total == 0:
            return
        term_count: dict[str, int] = {}
        for t in tokens:
            term_count[t] = term_count.get(t, 0) + 1
        for term, count in term_count.items():
            tf = count / total
            self._term_index[term][product_id] = tf

    def _tfidf_score(self, product_id1: str, product_id2: str) -> float:
        """두 상품 설명의 TF-IDF 코사인 유사도를 계산한다."""
        if self._doc_count < 2:
            return 0.0

        def get_vector(pid: str) -> dict[str, float]:
            vec: dict[str, float] = {}
            for term, docs in self._term_index.items():
                if pid in docs:
                    df = len(docs)
                    idf = math.log((self._doc_count + 1) / (df + 1)) + 1.0
                    vec[term] = docs[pid] * idf
            return vec

        v1 = get_vector(product_id1)
        v2 = get_vector(product_id2)
        if not v1 or not v2:
            return 0.0

        common = set(v1) & set(v2)
        if not common:
            return 0.0

        dot = sum(v1[t] * v2[t] for t in common)
        norm1 = math.sqrt(sum(s * s for s in v1.values()))
        norm2 = math.sqrt(sum(s * s for s in v2.values()))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot / (norm1 * norm2)

    def attribute_score(self, p1: ProductVector, p2: ProductVector) -> float:
        """두 상품의 가중 속성 유사도 점수를 계산한다."""
        score = 0.0
        if p1.category == p2.category:
            score += _ATTR_WEIGHT["category"]
        if p1.brand and p1.brand == p2.brand:
            score += _ATTR_WEIGHT["brand"]
        if p1.price_tier == p2.price_tier:
            score += _ATTR_WEIGHT["price_tier"]
        # 태그 Jaccard 유사도
        tags1 = set(p1.tags)
        tags2 = set(p2.tags)
        if tags1 or tags2:
            jaccard = len(tags1 & tags2) / len(tags1 | tags2) if (tags1 | tags2) else 0.0
            score += _ATTR_WEIGHT["tags"] * jaccard
        if p1.origin_country and p1.origin_country == p2.origin_country:
            score += _ATTR_WEIGHT["origin_country"]
        return score

    def similar(self, product_id: str, top_n: int = 10) -> list[RecommendationResult]:
        """유사한 상품 목록을 반환한다."""
        target = self._products.get(product_id)
        if target is None:
            return []

        results: list[RecommendationResult] = []
        for pid, prod in self._products.items():
            if pid == product_id:
                continue
            attr_score = self.attribute_score(target, prod)
            tfidf = self._tfidf_score(product_id, pid)
            total = attr_score + tfidf * 2.0
            if total > 0:
                results.append(
                    RecommendationResult(
                        product_id=pid,
                        score=total,
                        strategy="content_based",
                        reason=f"속성 유사도: {attr_score:.2f}, 설명 유사도: {tfidf:.2f}",
                    )
                )

        results.sort(key=lambda r: -r.score)
        return results[:top_n]

    def recommend_for_user(
        self,
        liked_product_ids: list[str],
        top_n: int = 10,
    ) -> list[RecommendationResult]:
        """사용자가 좋아한 상품들을 기반으로 유사 상품을 추천한다."""
        liked_set = set(liked_product_ids)
        scores: dict[str, float] = {}

        for pid in liked_product_ids:
            for rec in self.similar(pid, top_n=top_n * 2):
                if rec.product_id not in liked_set:
                    scores[rec.product_id] = scores.get(rec.product_id, 0.0) + rec.score

        sorted_items = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
        return [
            RecommendationResult(
                product_id=pid,
                score=score,
                strategy="content_based_user",
                reason="관심 상품 기반 콘텐츠 추천",
            )
            for pid, score in sorted_items
        ]
