"""재고 트랜잭션 유효성 검증."""
from __future__ import annotations
from .transaction_manager import TransactionManager
from .stock_ledger import StockLedger

VALID_TYPES = {"inbound", "outbound", "adjustment", "transfer"}

class TransactionValidator:
    def __init__(self, manager: TransactionManager | None = None) -> None:
        self._mgr = manager or TransactionManager()
        self._ledger = StockLedger(self._mgr)

    def validate(self, sku: str, tx_type: str, quantity: int) -> tuple[bool, list[str]]:
        errors = []
        if tx_type not in VALID_TYPES:
            errors.append(f"유효하지 않은 트랜잭션 유형: {tx_type}")
        if quantity == 0:
            errors.append("수량은 0이 될 수 없습니다")
        if tx_type == "outbound":
            current = self._ledger.current_qty(sku)
            if current - quantity < 0:
                errors.append(f"재고 부족: 현재 {current}, 출고 요청 {quantity}")
        return (len(errors) == 0, errors)
