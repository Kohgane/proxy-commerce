"""tests/test_v34_my_workspace.py — v34 P0: 마이페이지=개인 전용 작업공간(에디토리얼+내 실데이터)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ME = Path("src/seller_console/templates/me.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_me_template_editorial_and_kpi():
    # 에디토리얼 격상 + 작업공간 KPI 스트립(내 실데이터)
    assert "MY WORKSPACE" in ME                    # 오버라인 키커
    assert "console-stat-value" in ME              # 세리프 대형 KPI 숫자
    assert "내 작업공간" in ME
    for label in ("수집 상품", "연동 마켓", "내 소싱처", "보유 토큰"):
        assert label in ME, f"KPI 라벨 {label} 누락"
    assert "내 요금제" in ME                         # 플랜 카드
    assert "bg-primary" not in ME                   # 제네릭 보라 아바타 제거(토큰 var(--teal))


def test_me_renders_editorial_header(client):
    # 에디토리얼 헤더는 사용자 레코드 유무와 무관하게 렌더(200)
    with client.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "demo@goga.kr"
    resp = client.get("/seller/me")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "내 작업공간" in html
    assert "MY WORKSPACE" in html
