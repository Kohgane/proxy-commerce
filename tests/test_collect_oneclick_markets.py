"""tests/test_collect_oneclick_markets.py — 수집 페이지 원클릭 수집 지원 마켓 (퍼센티 벤치마킹).

GET /seller/collect 가 '원클릭 수집 지원 마켓' 버튼 행 + 크롬확장 인페이지 수집 안내를 렌더한다.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_collect_page_renders_oneclick_markets(client):
    resp = client.get("/seller/collect")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "원클릭 수집 지원 마켓" in html
    # 대표 소싱 마켓 링크가 포함됨
    assert "taobao.com" in html
    assert "aliexpress.com" in html
    assert "1688.com" in html
    # 퍼센티식 인페이지 수집(크롬확장) 안내
    assert "인페이지 수집" in html
    assert 'class="btn btn-outline-primary btn-sm oneclick-market"' in html


def test_collect_page_mentions_listing_multi_collect(client):
    """목록/검색 페이지 여러 상품 한 번에 수집(크롬확장 v1.4) 안내 노출."""
    html = client.get("/seller/collect").get_data(as_text=True)
    assert "검색·목록 페이지" in html
    assert "여러 상품" in html
