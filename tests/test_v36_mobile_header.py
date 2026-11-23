"""tests/test_v36_mobile_header.py — v36 PART A: 모바일 단일 헤더 압축."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
CONSOLE_CSS = Path("src/seller_console/static/console.css").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_console_topbar_hidden_on_mobile():
    # 공통 topbar(검색/수출형/언어/계정 나열)를 모바일에서 숨김
    assert ".console-topbar {\n    display: none;" in CONSOLE_CSS


def test_mobile_header_single_and_touch_targets():
    # 오너 11-23 개정: 모바일 헤더 = 공용 셸의 얇은 바(뒤로·제목·검색) — 로고·아바타는 빠졌다(계정은 「더보기」)
    assert "ms.topbar(" in BASE
    assert "toggleMobileSearch()" in BASE
    assert 'id="mobileSearch"' in BASE
    # 44px 터치 타깃
    assert "width: 44px; height: 44px" in CONSOLE_CSS
    # 모바일 드로어 언어 토글(공통 topbar가 숨겨지므로)
    assert "d-md-none" in BASE and "lang=ko" in BASE


def test_dashboard_renders_with_mobile_header(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert 'class="kgp-mtop"' in html                                 # 오너 11-23: 공용 셸 얇은 바
    assert 'id="mobileSearch"' in html
