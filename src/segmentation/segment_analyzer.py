"""src/segmentation/segment_analyzer.py — 세그먼트별 통계."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class SegmentAnalyzer:
    """세그먼트별 통계 분석 (크기, 평균 주문금액, LTV, 이탈률)."""

    def analyze(self, segment_name: str, customers: List[Dict[str, Any]]) -> dict:
        """세그먼트 고객 목록으로 통계 계산."""
        if not customers:
            return {
                "segment_name": segment_name,
                "size": 0,
                "avg_order_amount": 0.0,
                "ltv": 0.0,
                "churn_rate": 0.0,
                "avg_purchase_count": 0.0,
            }

        size = len(customers)
        total_amount = sum(float(c.get("total_purchase_amount", 0)) for c in customers)
        total_count = sum(float(c.get("purchase_count", 0)) for c in customers)

        avg_order_amount = total_amount / size if size else 0.0
        avg_purchase_count = total_count / size if size else 0.0

        # LTV: 평균 구매금액 × 평균 구매 횟수
        ltv = avg_order_amount * avg_purchase_count if avg_purchase_count > 0 else avg_order_amount

        # 이탈률: 90일 이상 미구매 고객 비율
        churned = sum(
            1 for c in customers
            if float(c.get("days_since_last_purchase", 0)) >= 90
        )
        churn_rate = churned / size if size else 0.0

        return {
            "segment_name": segment_name,
            "size": size,
            "avg_order_amount": round(avg_order_amount, 2),
            "ltv": round(ltv, 2),
            "churn_rate": round(churn_rate, 4),
            "avg_purchase_count": round(avg_purchase_count, 2),
        }

    def compare(self, results: List[dict]) -> dict:
        """여러 세그먼트 비교 요약."""
        if not results:
            return {"segments": [], "best_ltv": None, "largest": None}
        best_ltv = max(results, key=lambda r: r.get("ltv", 0))
        largest = max(results, key=lambda r: r.get("size", 0))
        return {
            "segments": results,
            "best_ltv": best_ltv.get("segment_name"),
            "largest": largest.get("segment_name"),
        }
