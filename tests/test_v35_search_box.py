"""tests/test_v35_search_box.py — v35 P1: 소싱 상품 검색창 크게·넓게 + 글자 위계."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

SOURCING = Path("src/seller_console/templates/sourcing.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_search_box_large_with_icon():
    # 큰 검색창(높이 ≥44px) + 돋보기 아이콘 프리픽스 + 또렷한 본문 글자
    assert "src-search" in SOURCING
    assert "min-height:54px" in SOURCING                  # ≥44px
    assert "input-group-text" in SOURCING                 # 돋보기 프리픽스 컨테이너
    assert "font-size:1.08rem" in SOURCING                # 또렷한 입력 글자(≥17px)
    # 타입 위계: 오버라인 라벨 + 큰 질문 라벨
    assert "상품 발굴" in SOURCING
    assert "font-size:1.12rem" in SOURCING
    assert "border-primary" not in SOURCING               # 제네릭 파랑 보더 제거(토큰 보더)


def test_search_renders(client):
    html = client.get("/seller/sourcing").get_data(as_text=True)
    assert "무슨 상품을 팔까요" in html
    assert "AI 상품 추천받기" in html
