"""tests/test_v33_card_status.py — v33 3-5: 소싱 카드 확대 + 주문 상태값 한글화(EN 화면 영문)."""
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


def test_sourcing_card_enlarged_and_no_emoji():
    # 상품 카드 이미지 큼직 + 글자 상향 + 버튼 패딩, 검색 링크 이모지 제거
    assert "height:180px" in SOURCING            # 큰 이미지
    assert "font-size:1.06rem" in SOURCING        # 제목 ≥17px
    assert "font-size:1.15rem" in SOURCING        # 가격 강조
    assert "btn btn-cta w-100 py-2" in SOURCING   # 버튼 패딩
    assert "{{ s.emoji }}" not in SOURCING        # 이모지 제거


def test_orders_status_korean_on_ko(client):
    html = client.get("/seller/orders").get_data(as_text=True)
    for ko in ("배송중", "배송완료", "신규접수", "환불요청"):
        assert ko in html, f"상태 한글 라벨 {ko} 누락"
    assert ">shipped<" not in html               # 원시 enum 노출 0


def test_orders_status_english_on_en(client):
    client.set_cookie("kgp_lang", "en")
    html = client.get("/seller/orders").get_data(as_text=True)
    # EN 화면은 영문 enum 유지
    assert ">shipped<" in html or "shipped" in html
