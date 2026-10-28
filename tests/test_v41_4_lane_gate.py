"""V41-4(오너 2026-10-28 18:14 「애플처럼 — 간결·군더더기 없이」) — 레인 게이트 = 에디토리얼: 카드 0·버튼 0·다리 하나·행 전체가 링크."""
from __future__ import annotations

import os
import re

import pytest

APP_CSS = open("src/static/app.css", encoding="utf-8").read()
BLOCK = APP_CSS[APP_CSS.index("V41-4 레인 게이트"):]


@pytest.fixture()
def client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_gate_has_no_app_chrome_and_one_bridge(client):
    html = client.get("/lane").get_data(as_text=True)
    assert 'data-role="lane-gate-bar"' in html and html.count('class="lane-gate-bridge"') == 1
    assert "OAuth 로그인" not in html and 'class="topnav' not in html          # 공통 탑내비(장바구니 마크·메뉴) 0
    assert html.count('data-role="lane-card"') == 3 and "<button" not in html[html.index('data-role="lane-list"'):]
    assert html.count('class="lane-card-keystone"') == 1                     # 키스톤 = 추천 레인 하나


def test_rows_not_cards():
    card = re.search(r"\.lane-card \{([^}]*)\}", BLOCK).group(1)
    assert "border: 0" in card and "box-shadow: none" in card and "display: grid" in card
    assert "border-top: 1px solid var(--border)" in BLOCK and "border-bottom: 1px solid var(--border)" in BLOCK   # 헤어라인
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", BLOCK) and "border-radius: 50%" not in BLOCK


def test_mobile_and_motion_guards():
    assert "@media (max-width: 767.98px)" in BLOCK and "min-height: 44px" in BLOCK
    assert "@media (prefers-reduced-motion: reduce)" in BLOCK
    assert "word-break: keep-all" in re.search(r"\.lane-gate-title \{([^}]*)\}", BLOCK).group(1)
