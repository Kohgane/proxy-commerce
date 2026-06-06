from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_pricing_apply_updates_catalog_and_returns_simulation_notice(client):
    from src.seller_console.market_status import AllMarketStatus, MarketStatusItem

    item = MarketStatusItem(
        marketplace="coupang",
        product_id="P-001",
        state="active",
        sku="SKU-001",
        title="테스트 상품",
        price_krw=10000,
        last_synced_at=datetime.utcnow(),
    )
    fetched = AllMarketStatus(summaries=[], items=[item], source="sheets")

    with patch("src.seller_console.market_status_sheets.MarketStatusSheetsAdapter.fetch_all", return_value=fetched), patch(
        "src.seller_console.market_status_sheets.MarketStatusSheetsAdapter.upsert_item", return_value=True
    ), patch(
        "src.seller_console.market_adapters.coupang_adapter.CoupangAdapter.update_price",
        return_value={"updated": False, "reason": "missing_credentials"},
    ):
        resp = client.post(
            "/seller/pricing/apply",
            json={
                "marketplace": "coupang",
                "product_id": "P-001",
                "sku": "SKU-001",
                "price": 15500,
            },
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["new_price"] == 15500
    assert "로컬" in data["message"]


def test_order_status_transition_endpoint_updates_status(client):
    from src.seller_console.orders.models import OrderStatus, UnifiedOrder

    svc = MagicMock()
    svc.list_orders.return_value = [
        UnifiedOrder(
            order_id="CP-001",
            marketplace="coupang",
            status=OrderStatus.PAID,
            placed_at=datetime(2024, 1, 1, 10, 0, 0),
            total_krw=Decimal("12000"),
        )
    ]
    svc.update_status.return_value = {"ok": True, "status": "preparing", "adapter": {"applied": False, "simulated": True}}

    with patch("src.seller_console.views._get_order_sync_service", return_value=svc):
        resp = client.post(
            "/seller/orders/coupang/CP-001/status",
            json={"next_status": "preparing"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["status"] == "preparing"
    svc.update_status.assert_called_once()


def test_order_status_transition_rejects_invalid_path(client):
    from src.seller_console.orders.models import OrderStatus, UnifiedOrder

    svc = MagicMock()
    svc.list_orders.return_value = [
        UnifiedOrder(
            order_id="CP-001",
            marketplace="coupang",
            status=OrderStatus.NEW,
            placed_at=datetime(2024, 1, 1, 10, 0, 0),
            total_krw=Decimal("12000"),
        )
    ]

    with patch("src.seller_console.views._get_order_sync_service", return_value=svc):
        resp = client.post(
            "/seller/orders/coupang/CP-001/status",
            json={"next_status": "delivered"},
        )

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "허용되지 않은 상태 전이" in data["error"]
