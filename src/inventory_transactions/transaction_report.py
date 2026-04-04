"""재고 트랜잭션 리포트."""
from __future__ import annotations
from .transaction_manager import TransactionManager

class TransactionReport:
    def __init__(self, manager: TransactionManager | None = None) -> None:
        self._mgr = manager or TransactionManager()

    def period_summary(self, start: str, end: str) -> dict:
        txs = [t for t in self._mgr.list() if start <= t.timestamp <= end]
        inbound = sum(t.quantity for t in txs if t.type == "inbound")
        outbound = sum(t.quantity for t in txs if t.type == "outbound")
        return {"start": start, "end": end, "inbound": inbound, "outbound": outbound, "count": len(txs)}

    def sku_history(self, sku: str) -> list[dict]:
        return [
            {"transaction_id": t.transaction_id, "type": t.type, "quantity": t.quantity, "timestamp": t.timestamp}
            for t in self._mgr.list(sku)
        ]

    def detect_discrepancies(self) -> list[dict]:
        """음수 재고 감지."""
        skus = {t.sku for t in self._mgr.list()}
        discrepancies = []
        for sku in skus:
            stats = self._mgr.stats(sku)
            if stats["net"] < 0:
                discrepancies.append({"sku": sku, "net_qty": stats["net"]})
        return discrepancies
