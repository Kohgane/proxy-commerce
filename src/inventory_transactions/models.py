"""재고 트랜잭션 데이터 모델."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class InventoryTransaction:
    transaction_id: str
    sku: str
    type: str  # inbound/outbound/adjustment/transfer
    quantity: int
    reason: str
    timestamp: str
    user_id: str = ""
    reference_id: str = ""
