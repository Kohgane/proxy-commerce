"""tests/test_for_beginners_v14.py — v14 For Beginners 고정 버튼 + 친절 카피 가드."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")


def test_for_beginners_fixed_button_with_toggle():
    assert "fbBtn" in BASE and "처음이신가요" in BASE         # 큰 진입 버튼
    assert "position:fixed" in BASE                          # 모든 페이지 고정
    assert "fbHide" in BASE and "fbReopen" in BASE           # 바로 밑 on/off
    assert "kgp_fb_hidden" in BASE                           # 상태 기억(localStorage)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_fixed_button_on_every_page(client):
    for path in ["/seller/dashboard", "/seller/collect", "/seller/markets", "/seller/orders"]:
        html = client.get(path).get_data(as_text=True)
        assert "fbBtn" in html, f"{path}에 For Beginners 고정 버튼 없음"


def test_collect_has_friendly_explainer(client):
    html = client.get("/seller/collect").get_data(as_text=True)
    assert "상품 수집이란?" in html                           # 원숭이도 이해 친절 카피
