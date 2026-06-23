"""tests/test_market_icons_v14.py — v14 기본 마켓 로고 아이콘 + 니치 제외 가드."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_oneclick_markets_use_site_logos(client):
    html = client.get("/seller/collect").get_data(as_text=True)
    assert "s2/favicons?domain=" in html          # 각 사이트 로고(파비콘) 아이콘 표시
    assert "domain=taobao.com" in html


def test_oneclick_big_markets_only(client):
    html = client.get("/seller/collect").get_data(as_text=True)
    # 대형 크로스보더 마켓
    for name in ("타오바오", "테무", "아마존", "알리익스프레스", "1688"):
        assert name in html
    # 니치/브랜드 사이트는 기본 제외(확장 '소싱처 관리'에서 직접 추가)
    for niche in ("요시다카반", "ZOZOTOWN", "VVIC"):
        assert niche not in html
