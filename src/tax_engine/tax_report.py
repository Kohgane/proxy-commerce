"""세금 리포트."""
from __future__ import annotations
from datetime import datetime

class TaxReport:
    def __init__(self) -> None:
        self._records: list[dict] = []

    def record(self, amount: float, tax: float, category: str = "", timestamp: str = "") -> None:
        self._records.append({
            "amount": amount,
            "tax": tax,
            "category": category,
            "timestamp": timestamp or datetime.now().isoformat(),
        })

    def period_summary(self, start: str, end: str) -> dict:
        records = [r for r in self._records if start <= r["timestamp"] <= end]
        total_amount = sum(r["amount"] for r in records)
        total_tax = sum(r["tax"] for r in records)
        return {"start": start, "end": end, "total_amount": total_amount, "total_tax": round(total_tax, 2), "count": len(records)}

    def by_category(self) -> dict:
        result: dict[str, float] = {}
        for r in self._records:
            cat = r.get("category", "기타")
            result[cat] = result.get(cat, 0) + r["tax"]
        return result
