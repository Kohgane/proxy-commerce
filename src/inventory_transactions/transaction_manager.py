"""재고 트랜잭션 관리자."""
from __future__ import annotations
import uuid
from datetime import datetime
from .models import InventoryTransaction

class TransactionManager:
    def __init__(self) -> None:
        self._transactions: list[InventoryTransaction] = []

    def create(self, sku: str, tx_type: str, quantity: int, reason: str = "", user_id: str = "", reference_id: str = "") -> InventoryTransaction:
        tx = InventoryTransaction(
            transaction_id=str(uuid.uuid4()),
            sku=sku,
            type=tx_type,
            quantity=quantity,
            reason=reason,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            reference_id=reference_id,
        )
        self._transactions.append(tx)
        return tx

    def list(self, sku: str | None = None) -> list[InventoryTransaction]:
        if sku is None:
            return list(self._transactions)
        return [t for t in self._transactions if t.sku == sku]

    def stats(self, sku: str | None = None) -> dict:
        txs = self.list(sku)
        inbound = sum(t.quantity for t in txs if t.type == "inbound")
        outbound = sum(t.quantity for t in txs if t.type == "outbound")
        adjustment = sum(t.quantity for t in txs if t.type == "adjustment")
        return {
            "total": len(txs),
            "inbound": inbound,
            "outbound": outbound,
            "adjustment": adjustment,
            "net": inbound - outbound + adjustment,
        }
