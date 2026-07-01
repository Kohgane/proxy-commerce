"""tests/test_market_connect_stepper_v14.py — v14 마켓 연동 순차 스테퍼 + 쿠팡 스코프 가드."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

HTML = Path("src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")


def test_sequential_stepper_present():
    assert "mcStepper" in HTML
    assert "한 마켓씩" in HTML
    assert "mc-market-nav" in HTML          # v40-C 2단 좌 마켓 내비
    assert "mc-market-col" in HTML
    assert 'data-connected="{{' in HTML            # 연결 상태로 자동 체크


def test_section_scoped_to_market():
    # 쿠팡 출고지 등 섹션이 '해당 마켓에만 필요'로 스코프 명시
    assert "이 항목은" in HTML and "에만 필요해요" in HTML


def test_dev_doc_note_removed():
    assert "LIVE_VERIFICATION_GUIDE" not in HTML    # 개발 문서 경로 노출 제거


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_connect_page_renders(client):
    html = client.get("/seller/markets/connect").get_data(as_text=True)
    assert html.count('class="') > 0 and "mcStepper" in html
