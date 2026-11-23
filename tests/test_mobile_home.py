"""tests/test_mobile_home.py — 모바일 앱 셸 (Phase 256, v3 P1-6)."""
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


@pytest.fixture(autouse=True)
def _clear():
    from src.seller_console import collect_history_store as chs
    chs._in_memory.clear()
    yield
    chs._in_memory.clear()


def test_mobile_home_renders_tabs(client):
    html = client.get("/seller/m").get_data(as_text=True)
    assert "BETA" in html and 'class="m-beta kgp-web-only"' in html      # 오너 11-23: 앱·설치형 안에선 숨김
    # 오너 11-23: 공용 셸 하단 4탭(수집·목록·주문·더보기) — 칸은 ?tab= 으로 서버가 고른다
    for href in ("/seller/m", "/seller/collect/history", "/seller/orders", "/seller/m?tab=more"):
        assert f'href="{href}"' in html
    assert 'data-pane="collect"' in html
    assert 'data-pane="orders"' in client.get("/seller/m?tab=orders").get_data(as_text=True)
    assert 'data-pane="more"' in client.get("/seller/m?tab=more").get_data(as_text=True)
    # 수집 폼은 기존 quick 수집 경로로
    assert 'action="/seller/collect/quick"' in html


def test_mobile_home_shows_recent_collect(client):
    from src.seller_console import collect_history_store as chs
    chs.append(source="manual", url="https://x/1", title="가방A", price="100", currency="USD",
               image="https://i/a.jpg", seller_id="default")
    html = client.get("/seller/m").get_data(as_text=True)
    assert "가방A" in html
    assert "https://i/a.jpg" in html


def test_mobile_home_has_install_pwa(client):
    """설치형 PWA — '앱 설치' 버튼 + beforeinstallprompt + manifest 링크."""
    html = client.get("/seller/m").get_data(as_text=True)
    assert "installBtn" in html and "beforeinstallprompt" in html
    assert "manifest.webmanifest" in html


def test_mobile_home_orders_kpi_real(client):
    fake = {"today_new": 4, "pending_ship": 2, "shipped": 9, "returned_exchanged": 1}
    with patch("src.seller_console.orders.sync_service.OrderSyncService") as MockSvc:
        MockSvc.return_value.kpi_summary.return_value = fake
        MockSvc.return_value.list_orders.return_value = []
        html = client.get("/seller/m?tab=orders").get_data(as_text=True)
    assert ">4<" in html and ">9<" in html
