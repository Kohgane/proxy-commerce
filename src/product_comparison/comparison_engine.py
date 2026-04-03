"""상품 비교 통합 엔진."""
from __future__ import annotations
from .attribute_comparer import AttributeComparer
from .price_comparer import PriceComparer
from .feature_matrix import FeatureMatrix
from .comparison_score import ComparisonScore
from .comparison_history import ComparisonHistory

class ComparisonEngine:
    def __init__(self) -> None:
        self._attr = AttributeComparer()
        self._price = PriceComparer()
        self._matrix = FeatureMatrix()
        self._score = ComparisonScore()
        self._history = ComparisonHistory()

    def compare(self, products: list[dict], user_id: str = "") -> dict:
        product_ids = [p.get("product_id", "") for p in products]
        cs = self._history.save(product_ids, user_id)
        return {
            "comparison_id": cs.comparison_id,
            "attributes": self._attr.compare(products),
            "prices": self._price.compare(products),
            "scores": self._score.calculate(products),
        }

    def history(self, user_id: str | None = None) -> list[dict]:
        return [
            {"comparison_id": h.comparison_id, "product_ids": h.product_ids, "created_at": h.created_at}
            for h in self._history.list(user_id)
        ]
