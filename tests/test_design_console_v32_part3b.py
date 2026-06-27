"""tests/test_design_console_v32_part3b.py — v32 PART3 #2: orders/markets 콘솔 디자인 격상."""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_orders_kpi_editorial_upgrade(client):
    html = client.get("/seller/orders").get_data(as_text=True)
    # 대시보드와 동일 패턴: 세리프 대형 KPI + 오버라인 라벨 + 토큰 악센트 카드 + 금 헤어라인
    assert "console-stat-value" in html
    assert "console-kpi-label" in html
    assert "console-kpi-card" in html
    assert "pc-hairline" in html
    # 옛 마크업/글리프 잔재 0
    assert "fs-2 fw-bold text-primary" not in html
    assert "⟳" not in html               # 단일 아이콘셋(bi-*)으로 교체


def test_markets_header_overline(client):
    html = client.get("/seller/markets").get_data(as_text=True)
    assert "console-kpi-label" in html   # 오버라인 라벨(에디토리얼 키커)
