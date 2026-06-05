from __future__ import annotations

import os
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _build_client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    return app.test_client()


def test_orders_auto_page_renders_action():
    with _build_client() as client:
        resp = client.get("/seller/orders/auto")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "주문 자동 처리 큐" in html
    assert "자동 처리 실행" in html


def test_orders_auto_process_returns_simulation_when_service_missing():
    with _build_client() as client:
        with patch("src.seller_console.views._get_order_sync_service", return_value=None):
            resp = client.post("/seller/orders/auto/process")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["mode"] == "simulation"
    assert "summary" in data


def test_orders_auto_process_reports_manual_and_pending_states():
    from src.seller_console.orders.models import OrderLineItem, OrderStatus, UnifiedOrder

    svc = MagicMock()
    svc.list_orders.return_value = [
        UnifiedOrder(
            order_id="ORD-PAID-1",
            marketplace="coupang",
            status=OrderStatus.PAID,
            placed_at=datetime(2026, 6, 1, 10, 0),
            total_krw=Decimal("10000"),
            items=[OrderLineItem(sku="SKU-1", title="상품1", qty=1, unit_price_krw=Decimal("10000"))],
        ),
        UnifiedOrder(
            order_id="ORD-REFUND-1",
            marketplace="smartstore",
            status=OrderStatus.REFUND_REQUESTED,
            placed_at=datetime(2026, 6, 1, 11, 0),
            total_krw=Decimal("12000"),
            items=[],
        ),
    ]

    with _build_client() as client:
        with patch("src.seller_console.views._get_order_sync_service", return_value=svc):
            resp = client.post("/seller/orders/auto/process")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["mode"] == "live"
    statuses = {item["status"] for item in data["results"]}
    assert "manual_required" in statuses
    assert "simulation_pending" in statuses
