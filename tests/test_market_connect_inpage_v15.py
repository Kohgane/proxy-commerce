"""tests/test_market_connect_inpage_v15.py — v15 P0-2 마켓 연결 인페이지 클릭플로우 가드."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

HTML = Path("src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")


def test_no_app_popup_windows():
    # 우리 앱은 새 창/팝업을 띄우지 않는다(발급 외부링크만 새 탭).
    assert "window.open" not in HTML


def test_inpage_three_step_flow():
    for s in ("연결 3단계", "① 키 발급받기", "② 받은 키 붙여넣기", "③ 저장하고 연결 테스트"):
        assert s in HTML
    assert "모두 이 화면에서 진행돼요" in HTML


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_issuance_link_only_new_tab(client):
    html = client.get("/seller/markets/connect").get_data(as_text=True)
    assert "이 버튼만 마켓 사이트가 새 탭" in html       # 발급 링크만 새 탭임을 명시
    assert "window.open" not in html
