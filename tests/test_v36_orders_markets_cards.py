"""tests/test_v36_orders_markets_cards.py — v36 PART A: 주문·마켓 표→모바일 카드."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ORDERS = Path("src/seller_console/templates/orders.html").read_text(encoding="utf-8")
MARKETS = Path("src/seller_console/templates/markets.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_orders_table_cards():
    assert "table-cards" in ORDERS
    for lbl in ('data-label="주문일시"', 'data-label="상품"', 'data-label="금액"',
                'data-label="상태"', 'data-label="운송장"'):
        assert lbl in ORDERS, f"{lbl} 누락"
    assert "cardcell-title" in ORDERS and "cardcell-actions" in ORDERS


def test_markets_table_cards():
    assert "table-cards" in MARKETS
    for lbl in ('data-label="상품 ID"', 'data-label="SKU"', 'data-label="상태"',
                'data-label="가격"', 'data-label="마지막 동기화"'):
        assert lbl in MARKETS, f"{lbl} 누락"
    assert "cardcell-title" in MARKETS


def test_orders_and_markets_render(client):
    assert client.get("/seller/orders").status_code == 200
    assert client.get("/seller/markets").status_code == 200
