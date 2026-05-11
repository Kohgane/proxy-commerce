"""src/orders/auto_processor.py — 주문 자동 처리 (Phase 145)."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass
class AutoOrder:
    order_id: str
    stage: str = "입금"
    stock_ok: bool = True
    address_ok: bool = True
    payment_ok: bool = True
    supplier: str = "rakuten"
    invoice_no: str = ""
    created_at: str = ""

    @property
    def needs_manual(self) -> bool:
        return not (self.stock_ok and self.address_ok and self.payment_ok)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["needs_manual"] = self.needs_manual
        return data


class OrderAutoProcessor:
    """인메모리 기반 주문 자동 처리기."""

    def __init__(self) -> None:
        self.enabled = os.getenv("ORDER_AUTO_PROCESS_ENABLED", "1") == "1"
        self.auto_place_po = os.getenv("ORDER_AUTO_PLACE_PO", "0") == "1"
        self._orders: list[AutoOrder] = []

    def enqueue(self, order_id: str, supplier: str = "rakuten", **flags) -> AutoOrder:
        order = AutoOrder(
            order_id=order_id,
            supplier=supplier,
            stage=str(flags.get("stage") or "입금"),
            stock_ok=bool(flags.get("stock_ok", True)),
            address_ok=bool(flags.get("address_ok", True)),
            payment_ok=bool(flags.get("payment_ok", True)),
            created_at=(flags.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )
        self._orders.append(order)
        return order

    def auto_review(self, order: AutoOrder) -> bool:
        return self.enabled and not order.needs_manual

    def create_purchase_order(self, order: AutoOrder) -> dict:
        return {
            "ok": self.auto_review(order) and self.auto_place_po,
            "supplier": order.supplier,
            "order_id": order.order_id,
        }

    def sync_invoice(self, order: AutoOrder, invoice_no: str) -> dict:
        order.invoice_no = invoice_no
        order.stage = "출고"
        return {"ok": True, "order_id": order.order_id, "invoice_no": invoice_no}

    def stage_notifications(self, order: AutoOrder) -> list[str]:
        return [f"{order.order_id}:{stage}" for stage in ("입금", "발주", "입고", "출고", "도착")]

    def queue(self) -> list[dict]:
        return [o.to_dict() for o in self._orders]

    def summary_24h(self) -> dict:
        manual = len([o for o in self._orders if o.needs_manual])
        auto = len(self._orders) - manual
        return {
            "new_orders_24h": len(self._orders),
            "auto_processed_24h": auto,
            "manual_intervention_24h": manual,
            "auto_place_po": self.auto_place_po,
            "invoice_sync_ok": True,
        }
