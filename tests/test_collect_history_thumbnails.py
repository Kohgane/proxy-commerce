"""tests/test_collect_history_thumbnails.py — 수집 이력에 썸네일/편집 버튼(퍼센티식 한눈에)."""
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


def test_history_shows_thumbnails_and_edit(client):
    items = [{
        "id": "a1", "collected_at": "2026-06-19T08:00:00", "source": "bookmarklet",
        "domain": "temu.com", "url": "https://temu.com/p", "title": "리클라이너 소파",
        "image_url": "https://img/x.jpg", "price": "55", "currency": "USD", "status": "ok",
    }]
    summary = {"total": 1, "today": 1, "domains": 1,
               "by_source": {"manual": 0, "bulk": 0, "extension": 0, "bookmarklet": 1}}
    with patch("src.seller_console.collect_history_store.list_items", return_value=items), \
         patch("src.seller_console.collect_history_store.summary", return_value=summary), \
         patch("src.seller_console.collect_history_store.distinct_domains", return_value=["temu.com"]):
        html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "https://img/x.jpg" in html        # 썸네일 이미지
    assert "object-fit:cover" in html          # 썸네일 스타일
    assert "편집·등록" in html                  # 편집·등록 버튼
    assert "리클라이너 소파" in html
