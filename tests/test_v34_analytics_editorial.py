"""tests/test_v34_analytics_editorial.py — v34 디자인 실집행: BI 분석 에디토리얼 격상."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ANALYTICS = Path("src/seller_console/templates/analytics.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_analytics_editorial_markup():
    # 대시보드/주문과 동형 에디토리얼: 오버라인 라벨 + 금 헤어라인 + 세리프 대형 KPI + 토큰 좌악센트
    assert "console-kpi-label" in ANALYTICS
    assert "pc-hairline" in ANALYTICS
    assert "console-stat-value" in ANALYTICS                 # 세리프 대형 매출 숫자
    assert "console-kpi-card" in ANALYTICS
    for accent in ("console-kpi-primary", "console-kpi-success", "console-kpi-warning"):
        assert accent in ANALYTICS, f"토큰 좌악센트 {accent} 누락"
    assert "fs-4 fw-bold" not in ANALYTICS                   # 제네릭 KPI 제거


def test_analytics_renders(client):
    html = client.get("/seller/analytics").get_data(as_text=True)
    assert "재고·판매 분석" in html
    assert "오늘 매출" in html
