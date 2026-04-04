"""재고 원장 — SKU별 현재 수량 계산."""
from __future__ import annotations
from .transaction_manager import TransactionManager

class StockLedger:
    def __init__(self, manager: TransactionManager | None = None) -> None:
        self._mgr = manager or TransactionManager()

    def current_qty(self, sku: str) -> int:
        return self._mgr.stats(sku)["net"]

    def snapshot(self, sku: str, as_of: str | None = None) -> dict:
        txs = self._mgr.list(sku)
        if as_of:
            txs = [t for t in txs if t.timestamp <= as_of]
        net = 0
        for t in txs:
            if t.type == "inbound":
                net += t.quantity
            elif t.type == "outbound":
                net -= t.quantity
            elif t.type == "adjustment":
                net += t.quantity
        return {"sku": sku, "quantity": net, "as_of": as_of}
