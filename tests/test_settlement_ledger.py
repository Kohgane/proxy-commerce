"""tests/test_settlement_ledger.py — 장부·정산 노출 (Phase 251, v3 P1-5 #5)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_settlement_page_200_and_ledger_framing(client):
    resp = client.get("/seller/settlement")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "장부" in html and "정산" in html
    # 도구 링크 노출(애널리틱스/마진)
    assert "/seller/analytics" in html
    assert "/seller/margin" in html


def test_settlement_shows_real_order_kpi(client):
    fake = {"today_new": 7, "pending_ship": 3, "shipped": 11, "returned_exchanged": 1}
    with patch("src.seller_console.orders.sync_service.OrderSyncService") as MockSvc:
        MockSvc.return_value.kpi_summary.return_value = fake
        resp = client.get("/seller/settlement")
    html = resp.get_data(as_text=True)
    assert ">7<" in html and ">11<" in html  # 실 주문 KPI 반영


def test_settlement_in_nav(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/settlement" in html
    assert "장부·정산" in html
