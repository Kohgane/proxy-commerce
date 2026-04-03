"""피킹 주문 생성 + 최적 경로 계산."""
from __future__ import annotations
import uuid
from datetime import datetime

class PickingOrder:
    def __init__(self) -> None:
        self._orders: dict[str, dict] = {}

    def create(self, order_id: str, items: list[dict]) -> dict:
        pick_id = str(uuid.uuid4())
        # 기본 정렬: 통로/열/층 순
        sorted_items = sorted(items, key=lambda x: (x.get("aisle", ""), x.get("row", 0), x.get("level", 0)))
        order = {
            "pick_id": pick_id,
            "order_id": order_id,
            "items": sorted_items,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        self._orders[pick_id] = order
        return order

    def complete(self, pick_id: str) -> dict:
        order = self._orders.get(pick_id, {})
        if order:
            order["status"] = "completed"
        return order

    def list(self) -> list[dict]:
        return list(self._orders.values())
