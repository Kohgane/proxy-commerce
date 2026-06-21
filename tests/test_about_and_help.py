"""tests/test_about_and_help.py — About 소개 + '?' 개발자문구 숨김 (Phase 254, v5)."""
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


def test_about_page_renders(client):
    html = client.get("/seller/about").get_data(as_text=True)
    assert "코고가네" in html
    assert "수집" in html and "등록" in html
    assert "/seller/start" in html  # 시작하기 CTA


def test_about_linked_from_landing(client, monkeypatch):
    monkeypatch.setenv("ROOT_REDIRECT", "landing")
    from src.order_webhook import app
    with app.test_client() as c:
        html = c.get("/").get_data(as_text=True)
    assert "/seller/about" in html


def test_markets_connect_dev_text_hidden_behind_help(client):
    """기술 문구(MARKET_CRED_ENC_KEY 등)는 본문 노출 대신 '?' 툴팁 안으로."""
    html = client.get("/seller/markets/connect").get_data(as_text=True)
    # 친절한 한 줄은 본문에, 기술 디테일은 tooltip data-bs-title 안에
    assert "안전하게 암호화" in html
    assert 'class="pc-help"' in html
    assert "MARKET_CRED_ENC_KEY" in html  # 툴팁 속성 안에 존재
    # 본문 단락에 길게 노출되던 '읽기/안전한 빈 쓰기' 설명이 평문 <strong>로 남지 않음
    assert "<strong>연결 테스트</strong>는 실제 마켓에 읽기" not in html
