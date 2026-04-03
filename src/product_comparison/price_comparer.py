"""가격 비교."""
from __future__ import annotations

class PriceComparer:
    def compare(self, products: list[dict]) -> dict:
        if not products:
            return {}
        result = []
        for p in products:
            cost = p.get("cost_price", 0)
            sell = p.get("sell_price", 0)
            margin = ((sell - cost) / sell * 100) if sell > 0 else 0
            result.append({
                "product_id": p.get("product_id", ""),
                "cost_price": cost,
                "sell_price": sell,
                "margin_pct": round(margin, 2),
            })
        min_price = min((r["sell_price"] for r in result), default=0)
        max_price = max((r["sell_price"] for r in result), default=0)
        return {"products": result, "min_price": min_price, "max_price": max_price}
