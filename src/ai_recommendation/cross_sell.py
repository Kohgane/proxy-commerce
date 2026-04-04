"""src/ai_recommendation/cross_sell.py — Phase 94: 크로스셀/업셀 엔진."""
from __future__ import annotations

from collections import defaultdict

from .recommendation_model import RecommendationResult

# 연관 규칙 최소 임계값
_MIN_SUPPORT = 0.01
_MIN_CONFIDENCE = 0.1
_MIN_LIFT = 1.0


class CrossSellEngine:
    """크로스셀/업셀 추천 엔진.

    - 함께 구매된 상품 분석 (연관 규칙 마이닝: support, confidence, lift)
    - 장바구니 기반 실시간 크로스셀 추천
    - 업셀 추천 (동일 카테고리 상위 가격대 상품)
    - 번들 추천 연동
    """

    def __init__(self) -> None:
        # transaction_id -> {product_id}
        self._transactions: dict[str, set[str]] = {}
        # 상품 메타: product_id -> {category, price, price_tier}
        self._product_meta: dict[str, dict] = {}
        # 번들 레지스트리: bundle_id -> [product_id]
        self._bundles: dict[str, list[str]] = {}

    def add_transaction(self, transaction_id: str, product_ids: list[str]) -> None:
        """구매 트랜잭션을 추가한다."""
        self._transactions[transaction_id] = set(product_ids)

    def register_product(
        self,
        product_id: str,
        category: str,
        price: float,
        price_tier: str = "mid",
    ) -> None:
        """상품 메타데이터를 등록한다."""
        self._product_meta[product_id] = {
            "category": category,
            "price": price,
            "price_tier": price_tier,
        }

    def register_bundle(self, bundle_id: str, product_ids: list[str]) -> None:
        """번들을 등록한다."""
        self._bundles[bundle_id] = product_ids

    def _compute_support(self, itemset: frozenset) -> float:
        """아이템셋의 support를 계산한다."""
        n = len(self._transactions)
        if n == 0:
            return 0.0
        count = sum(1 for t in self._transactions.values() if itemset.issubset(t))
        return count / n

    def get_association_rules(
        self,
        antecedent: str,
        min_confidence: float = _MIN_CONFIDENCE,
        min_lift: float = _MIN_LIFT,
        top_n: int = 10,
    ) -> list[dict]:
        """antecedent 상품 구매 시 함께 구매될 상품의 연관 규칙을 반환한다."""
        n = len(self._transactions)
        if n == 0:
            return []

        ant_set = frozenset([antecedent])
        support_ant = self._compute_support(ant_set)
        if support_ant == 0:
            return []

        # 함께 구매된 상품 카운트
        co_count: dict[str, int] = defaultdict(int)
        for t in self._transactions.values():
            if antecedent in t:
                for pid in t:
                    if pid != antecedent:
                        co_count[pid] += 1

        rules: list[dict] = []
        for pid, count in co_count.items():
            support_pair = count / n
            confidence = support_pair / support_ant
            support_cons = self._compute_support(frozenset([pid]))
            lift = confidence / support_cons if support_cons > 0 else 0.0

            if confidence >= min_confidence and lift >= min_lift:
                rules.append({
                    "product_id": pid,
                    "support": round(support_pair, 4),
                    "confidence": round(confidence, 4),
                    "lift": round(lift, 4),
                })

        rules.sort(key=lambda r: (-r["lift"], -r["confidence"]))
        return rules[:top_n]

    def cross_sell(
        self,
        product_ids: list[str],
        top_n: int = 5,
    ) -> list[RecommendationResult]:
        """장바구니 상품들을 기반으로 크로스셀 추천을 반환한다."""
        seen = set(product_ids)
        scores: dict[str, float] = defaultdict(float)

        for pid in product_ids:
            rules = self.get_association_rules(pid, top_n=top_n * 2)
            for rule in rules:
                rec_pid = rule["product_id"]
                if rec_pid not in seen:
                    # lift * confidence 기반 점수
                    scores[rec_pid] += rule["lift"] * rule["confidence"]

        sorted_items = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
        return [
            RecommendationResult(
                product_id=pid,
                score=score,
                strategy="cross_sell",
                reason="함께 구매된 상품 (연관 규칙)",
            )
            for pid, score in sorted_items
        ]

    def upsell(
        self,
        product_id: str,
        top_n: int = 3,
    ) -> list[RecommendationResult]:
        """동일 카테고리의 상위 가격대 상품을 추천한다 (업셀)."""
        target = self._product_meta.get(product_id)
        if not target:
            return []

        target_cat = target["category"]
        target_price = target["price"]
        _tier_order = {"low": 0, "mid": 1, "high": 2, "premium": 3}
        target_tier = _tier_order.get(target.get("price_tier", "mid"), 1)

        candidates: list[tuple[str, float]] = []
        for pid, meta in self._product_meta.items():
            if pid == product_id:
                continue
            if meta["category"] != target_cat:
                continue
            pid_tier = _tier_order.get(meta.get("price_tier", "mid"), 1)
            if pid_tier > target_tier or meta["price"] > target_price:
                score = meta["price"] / target_price if target_price > 0 else 1.0
                candidates.append((pid, score))

        candidates.sort(key=lambda x: x[1])
        return [
            RecommendationResult(
                product_id=pid,
                score=score,
                strategy="upsell",
                reason=f"상위 가격대 동일 카테고리 ({target_cat})",
            )
            for pid, score in candidates[:top_n]
        ]

    def bundle_recommend(
        self,
        product_id: str,
        top_n: int = 3,
    ) -> list[RecommendationResult]:
        """상품이 포함된 번들을 추천한다."""
        results: list[RecommendationResult] = []
        for bundle_id, bundle_products in self._bundles.items():
            if product_id in bundle_products:
                others = [p for p in bundle_products if p != product_id]
                for other_pid in others[:top_n]:
                    results.append(
                        RecommendationResult(
                            product_id=other_pid,
                            score=1.0,
                            strategy="bundle",
                            reason=f"번들 추천 ({bundle_id})",
                        )
                    )
        return results[:top_n]
