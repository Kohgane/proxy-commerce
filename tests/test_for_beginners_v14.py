"""tests/test_for_beginners_v14.py — v14 For Beginners 고정 버튼 + 친절 카피 가드."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")


def test_for_beginners_fixed_button_with_toggle():
    # Y12-A(오너 2026-10-17 d): 떠 있는 버튼은 모든 페이지에서 뺐다 — 시작 가이드는 사이드바 「시작 가이드」 한 곳
    assert "fbBtn" not in BASE and "fbReopen" not in BASE and "kgp_fb_hidden" not in BASE
    assert 'href="/seller/start" data-role="nav-start-guide"' in BASE


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_fixed_button_on_every_page(client):
    # Y12-A(오너 d): 어떤 페이지에도 떠 있는 버튼이 없고, 사이드바 「시작 가이드」는 어디서나 보인다
    for path in ["/seller/dashboard", "/seller/collect/history", "/seller/collect", "/seller/markets", "/seller/orders"]:
        html = client.get(path).get_data(as_text=True)
        assert "fbBtn" not in html and 'data-role="nav-start-guide"' in html, path


def test_collect_has_friendly_explainer(client):
    html = client.get("/seller/collect").get_data(as_text=True)
    assert "상품 수집이란?" in html                           # 원숭이도 이해 친절 카피
