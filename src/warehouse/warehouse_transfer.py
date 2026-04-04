"""창고 간 재고 이동."""
from __future__ import annotations
import uuid
from datetime import datetime

class WarehouseTransfer:
    STATUSES = ["pending", "in_transit", "received"]

    def __init__(self) -> None:
        self._transfers: dict[str, dict] = {}

    def create(self, from_warehouse_id: str, to_warehouse_id: str, items: list[dict]) -> dict:
        transfer_id = str(uuid.uuid4())
        transfer = {
            "transfer_id": transfer_id,
            "from_warehouse_id": from_warehouse_id,
            "to_warehouse_id": to_warehouse_id,
            "items": items,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        self._transfers[transfer_id] = transfer
        return transfer

    def advance(self, transfer_id: str) -> dict:
        t = self._transfers.get(transfer_id)
        if not t:
            return {}
        idx = self.STATUSES.index(t["status"])
        if idx < len(self.STATUSES) - 1:
            t["status"] = self.STATUSES[idx + 1]
        return t

    def list(self) -> list[dict]:
        return list(self._transfers.values())
