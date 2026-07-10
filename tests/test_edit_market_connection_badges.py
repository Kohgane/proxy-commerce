"""tests/test_edit_market_connection_badges.py — 편집 페이지 마켓 연동 상태 표시."""
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


def _item():
    return {"id": "x", "title": "t", "url": "https://shop/p", "image_url": "https://i/1.jpg",
            "price": "10", "currency": "USD", "extra_json": "{}"}


def test_edit_page_shows_connection_badges(client):
    # v51: 드로어가 connected_markets(배치 1회)로 판정 → 그걸 패치.
    with patch("src.seller_console.collect_history_store.get", return_value=_item()), \
         patch("src.seller_console.market_credentials.connected_markets",
               side_effect=lambda sid, markets: {m: (m in ("shopify", "coupang")) for m in markets}):
        html = client.get("/seller/collect/preview/x").get_data(as_text=True)
    assert "키 설정됨" in html and "bi-check-circle" in html   # 연결된 마켓(v18 아이콘셋)
    assert "미설정" in html and "bi-x-circle" in html         # 미연결 마켓
    assert "키 설정 2/5" in html          # 요약
    assert "/seller/markets/connect/smartstore" in html  # 미연결 → 연결 링크


def test_edit_page_all_connected_shows_full(client):
    with patch("src.seller_console.collect_history_store.get", return_value=_item()), \
         patch("src.seller_console.market_credentials.connected_markets",
               side_effect=lambda sid, markets: {m: True for m in markets}):
        html = client.get("/seller/collect/preview/x").get_data(as_text=True)
    assert "키 설정 5/5" in html
    assert "미설정</a>" not in html  # 미설정 배지 없음
