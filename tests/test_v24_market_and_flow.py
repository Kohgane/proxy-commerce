"""tests/test_v24_market_and_flow.py — v24 P0 마켓 Mock 정리 + P1 초보 흐름 가드."""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_markets_no_mock_jargon_for_users(client):
    """마켓 현황: 일반 유저에게 'Mock 모드'/'mock 데이터' 노출 0, 빈 상태는 친절 안내."""
    html = client.get("/seller/markets").get_data(as_text=True)
    assert "Mock 모드" not in html
    assert "mock 데이터" not in html
    # 섹션 의미 명확
    assert "마켓별 상품 등록·동기화 현황" in html
    # 데이터 없을 때(mock 폴백) 친절 빈 상태
    assert "아직 등록된 상품이 없어요" in html


def test_markets_keeps_connection_controls(client):
    """상단 연동 상태/컨트롤(실데이터)은 유지."""
    html = client.get("/seller/markets").get_data(as_text=True)
    assert "마켓 연동 컨트롤 센터" in html
    assert "/seller/markets/connect" in html


def test_collect_screen_has_next_step(client):
    """수집 화면: 초보 흐름 '다음 할 일' 한 줄 + 다음 단계 버튼."""
    html = client.get("/seller/collect").get_data(as_text=True)
    assert "다음 할 일" in html
    assert "수집한 상품 보기" in html


def test_collect_history_empty_state_keeps_extension_cta(client):
    """수집 이력 빈 상태: 크롬 확장 설치 + 수동 수집 안내 유지(현행)."""
    html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "크롬 확장 설치" in html
