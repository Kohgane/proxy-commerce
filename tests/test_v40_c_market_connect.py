"""tests/test_v40_c_market_connect.py — v40-C: 퍼센티식 마켓연동 화면.

좌마켓리스트(항상 표시) + 우상세(선택 마켓 폼, JS 전환·페이지 이탈 0),
연동상태 뱃지, 배송프로필 카드(쿠팡), 자격증명 마스킹.
기존 v14 스테퍼·v15 인페이지 3단계는 우상세 패널 안에 보존(회귀 0).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")


def test_two_column_layout_present():
    """퍼센티식 2열 래퍼 · 사이드바 · 상세 패널."""
    assert "mc-layout" in TPL
    assert "mc-sidebar" in TPL
    assert "mc-detail" in TPL


def test_sidebar_items_with_status_badges():
    """사이드바: mc-sidebar-item + data-role='status-badge' + JS 선택(data-mc-select)."""
    assert "mc-sidebar-item" in TPL
    assert 'data-role="status-badge"' in TPL
    assert "data-mc-select" in TPL or "mcSelect(" in TPL


def test_no_chip_page_navigation():
    """마켓 전환은 JS — chip <a href> 없음(페이지 이탈 0)."""
    chip_hrefs = re.findall(r'href="/seller/markets/connect/\w+"', TPL)
    assert not chip_hrefs, f"페이지 이탈 chip href 잔존: {chip_hrefs}"


def test_shipping_profile_label_for_coupang():
    """쿠팡: '배송프로필' 라벨(출고지·반품지 섹션 명시)."""
    assert "배송프로필" in TPL


def test_credential_masking_secret_fields():
    """secret 필드: type=password + 기존값은 마스킹 placeholder."""
    assert 'type="password"' in TPL
    assert "저장됨" in TPL          # 저장됨 (ab••••cd) 형태 표시


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_market_connect_renders_two_col(client):
    """마켓 연결 페이지 200 + mc-layout 포함."""
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    html = client.get("/seller/markets/connect").get_data(as_text=True)
    assert html.count("mc-layout") >= 1
    assert "mc-sidebar" in html and "mc-detail" in html


def test_all_markets_in_sidebar(client):
    """전체 마켓이 사이드바에 표시됨."""
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    html = client.get("/seller/markets/connect").get_data(as_text=True)
    for label in ("쿠팡", "스마트스토어", "Shopify", "WooCommerce"):
        assert label in html
