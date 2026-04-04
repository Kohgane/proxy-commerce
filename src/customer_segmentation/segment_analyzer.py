"""세그먼트 분석기."""
from __future__ import annotations

class SegmentAnalyzer:
    def analyze(self, segment_id: str, customers: list[dict]) -> dict:
        if not customers:
            return {"segment_id": segment_id, "count": 0, "avg_order_value": 0, "ltv": 0, "repurchase_rate": 0}
        avg_order = sum(c.get("avg_order_value", 0) for c in customers) / len(customers)
        ltv = sum(c.get("total_spend", 0) for c in customers) / len(customers)
        repurchasers = sum(1 for c in customers if c.get("purchase_count", 0) > 1)
        return {
            "segment_id": segment_id,
            "count": len(customers),
            "avg_order_value": round(avg_order, 2),
            "ltv": round(ltv, 2),
            "repurchase_rate": round(repurchasers / len(customers), 4),
        }
