"""tests/test_v35_search_box.py — v35 P1: 소싱 상품 검색창 크게·넓게 + 글자 위계."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

SOURCING = Path("src/seller_console/templates/sourcing.html").read_text(encoding="utf-8")
CSS = Path("src/static/app.css")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_search_box_large_with_icon():
    """v35 P1이 정한 치수는 그대로다 — **자리만 인라인에서 토큰 CSS로 옮겼다**(6-i).

    옛 계약은 인라인 문자열(`min-height:54px`)을 핀했는데, 그건 디자인 규율이 금지하는 자리다
    (하드코딩 hex/px 금지). 그래서 **같은 치수를 CSS 규칙에서** 확인한다 — 값이 줄면 여전히 실패한다.
    ※ 6-i에서 뷰포트 예산 때문에 46px로 줄였다가 되돌렸다: 오너 지시가 예산보다 위다.
    """
    css = CSS.read_text(encoding="utf-8")
    assert "si-search" in SOURCING                        # 검색 그룹(구 `src-search`)
    assert "min-height: 54px" in css                      # ≥44px — 크게(오너 v35 P1)
    assert "input-group-text" in SOURCING                 # 돋보기 프리픽스 컨테이너
    assert "font-size: 1.08rem" in css                    # 또렷한 입력 글자(≥17px)
    # 타입 위계: 오버라인 라벨 + 큰 질문 라벨
    assert "상품 발굴" in SOURCING or "무슨 상품을 팔까요" in SOURCING
    assert "font-size: 1.12rem" in css                    # 질문 라벨
    assert "border-primary" not in SOURCING               # 제네릭 파랑 보더 제거(토큰 보더)


def test_search_renders(client):
    html = client.get("/seller/sourcing").get_data(as_text=True)
    assert "무슨 상품을 팔까요" in html
    assert "AI 상품 추천받기" in html
