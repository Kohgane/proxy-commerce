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


def test_settlement_net_profit_kpis_and_missing_honesty(client):
    # Q1 #1: 장부 = 주문별 순이익 자동계산. 원가 미연결 주문은 '미입력' 정직(가짜 수치 0).
    class _FakeOrder:
        def to_dict(self):
            return {"order_id": "O1", "marketplace": "coupang", "total_krw": "50000",
                    "shipping_fee_krw": "0", "items": [{"sku": "NOLINK", "qty": 1}]}
    with patch("src.seller_console.orders.sync_service.OrderSyncService") as MockSvc:
        MockSvc.return_value.list_orders.return_value = [_FakeOrder()]
        resp = client.get("/seller/settlement")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # 순이익 KPI 라벨(주문 상태 카운트 아님).
    assert "실 순이익 합계" in html and "평균 마진율" in html and "원가 미연결" in html
    # 원가 미연결 주문 → 순이익 '미입력'(가짜 0 금지).
    assert "미입력" in html


def test_settlement_in_nav(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/settlement" in html
    assert "장부·정산" in html
