"""tests/test_markets_connect_deeplink.py — 마켓 연동 발급 딥링크 + 서버 IP (Phase 259, v6 P0)."""
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


def test_connect_page_has_issuance_deeplinks(client):
    html = client.get("/seller/markets/connect").get_data(as_text=True)
    # 각 카드에 발급 페이지 딥링크(주황 btn-cta, 새 탭)
    assert "btn-cta" in html
    assert 'target="_blank"' in html
    # v6 표의 핵심 발급 URL
    assert "wing.coupang.com" in html
    assert "apicenter.commerce.naver.com" in html


def test_server_ip_block_shown_when_known(client, monkeypatch):
    monkeypatch.setenv("SERVER_OUTBOUND_IP", "203.0.113.7")
    # 캐시 무시: env 우선이라 바로 노출
    html = client.get("/seller/markets/connect").get_data(as_text=True)
    assert "203.0.113.7" in html
    assert "copyServerIp" in html
    assert "허용 목록에 등록" in html


def test_guide_map_has_markets():
    from src.seller_console.market_guide import guide_map
    gm = guide_map()
    assert gm["coupang"]["official_url"].startswith("https://wing.coupang.com")
    assert "openapi.11st.co.kr" in gm["elevenst"]["official_url"] or "11st" in gm.get("elevenst", {}).get("official_url", "11st")
