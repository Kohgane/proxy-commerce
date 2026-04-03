"""재고 실사 조정."""
from __future__ import annotations
from .transaction_manager import TransactionManager
from .stock_ledger import StockLedger

class StockAdjustment:
    def __init__(self, manager: TransactionManager | None = None) -> None:
        self._mgr = manager or TransactionManager()
        self._ledger = StockLedger(self._mgr)

    def adjust(self, sku: str, actual_qty: int, reason: str = "stocktake", user_id: str = "") -> dict:
        current = self._ledger.current_qty(sku)
        diff = actual_qty - current
        if diff == 0:
            return {"sku": sku, "diff": 0, "status": "no_change"}
        tx = self._mgr.create(sku, "adjustment", diff, reason=reason, user_id=user_id)
        return {"sku": sku, "previous": current, "actual": actual_qty, "diff": diff, "transaction_id": tx.transaction_id}
