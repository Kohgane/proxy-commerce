"""종합 비교 점수 계산."""
from __future__ import annotations

class ComparisonScore:
    def calculate(self, products: list[dict], weights: dict[str, float] | None = None) -> list[dict]:
        if not products:
            return []
        weights = weights or {"price": -0.4, "rating": 0.4, "stock": 0.2}
        scores = []
        for p in products:
            score = sum(p.get(attr, 0) * w for attr, w in weights.items())
            scores.append({"product_id": p.get("product_id", ""), "score": round(score, 4)})
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores
