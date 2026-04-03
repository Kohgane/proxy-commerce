"""속성별 비교."""
from __future__ import annotations

class AttributeComparer:
    def compare(self, products: list[dict], attributes: list[str] | None = None) -> dict:
        if not products:
            return {}
        attributes = attributes or ["price", "weight", "rating", "category"]
        result: dict[str, dict] = {}
        for attr in attributes:
            result[attr] = {p.get("product_id", str(i)): p.get(attr) for i, p in enumerate(products)}
        return result
