from __future__ import annotations

from src.orders.auto_processor import OrderAutoProcessor


def test_order_auto_processor_queue_and_summary():
    proc = OrderAutoProcessor()
    proc.enqueue("ord-1", stock_ok=True, address_ok=True, payment_ok=True)
    proc.enqueue("ord-2", stock_ok=False, address_ok=True, payment_ok=True)

    queue = proc.queue()
    assert len(queue) == 2
    assert queue[1]["needs_manual"] is True

    summary = proc.summary_24h()
    assert summary["new_orders_24h"] == 2
    assert summary["manual_intervention_24h"] == 1


def test_sync_invoice_and_notifications():
    proc = OrderAutoProcessor()
    order = proc.enqueue("ord-3")
    result = proc.sync_invoice(order, "INV-123")
    assert result["ok"] is True
    assert order.stage == "출고"
    assert len(proc.stage_notifications(order)) == 5
