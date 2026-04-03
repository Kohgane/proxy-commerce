"""기능/스펙 비교 매트릭스 생성."""
from __future__ import annotations

class FeatureMatrix:
    def build(self, products: list[dict], features: list[str] | None = None) -> dict:
        if not products:
            return {"features": [], "matrix": []}
        all_features = features or list({k for p in products for k in p.keys() if k != "product_id"})
        matrix = []
        for p in products:
            row = {"product_id": p.get("product_id", ""), "features": {f: p.get(f) for f in all_features}}
            matrix.append(row)
        return {"features": all_features, "matrix": matrix}
