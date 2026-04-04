"""세금 계산서 데이터 생성."""
from __future__ import annotations
import uuid
from datetime import datetime

class TaxInvoice:
    def create(self, supplier: dict, buyer: dict, items: list[dict]) -> dict:
        total_amount = sum(i.get("amount", 0) for i in items)
        total_tax = sum(i.get("tax", 0) for i in items)
        return {
            "invoice_id": str(uuid.uuid4()),
            "issue_date": datetime.now().strftime("%Y-%m-%d"),
            "supplier": supplier,
            "buyer": buyer,
            "items": items,
            "subtotal": total_amount,
            "total_tax": round(total_tax, 2),
            "total": round(total_amount + total_tax, 2),
        }
