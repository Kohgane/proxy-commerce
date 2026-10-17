"""tests/test_v36_tables_cards.py — v36 PART A: 넓은 표→모바일 카드 + 플로팅 버튼 겹침 수정."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

HIST = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
CONSOLE_CSS = Path("src/seller_console/static/console.css").read_text(encoding="utf-8")
SELLER_CSS = Path("src/seller_console/static/seller.css").read_text(encoding="utf-8")
BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_collect_history_table_is_cardable():
    # Y12-A(오너 2026-10-17): 수집 목록은 카드가 아니라 **한 줄**(390px에서도) — 썸네일·상품명·뱃지·시각 4칸.
    #   가격·경로·수집 시각·상태는 드로어 맨 위 한 줄. 모바일 한 줄 규칙은 app.css `.ch-table`.
    assert "ch-table" in HIST and "table-cards" not in HIST
    ROWS = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    for cell in ("ch-c-chk", "ch-c-img", "ch-c-title", "ch-c-badges", "ch-c-when"):
        assert cell in ROWS, f"{cell} 누락"
    css = Path("src/static/app.css").read_text(encoding="utf-8")
    assert ".ch-table tr.ch-row { display: flex;" in css


def test_table_cards_mobile_css():
    # 모바일에서 표를 카드로 스택 + 액션 버튼 풀폭(≥44px)
    assert "table.table-cards > thead { display: none; }" in CONSOLE_CSS
    assert "td.cardcell-actions .btn" in CONSOLE_CSS
    assert "min-height: 44px" in CONSOLE_CSS


def test_global_table_minwidth_removed():
    # 전역 강제 min-width(가로 스크롤 유발) 제거 — table-cards 아닌 표만 컨테이너 내 스크롤
    assert "  table {\n    min-width: 600px;\n  }" not in SELLER_CSS
    assert ".table-responsive > table:not(.table-cards)" in SELLER_CSS


def test_for_beginners_fab_shrinks_on_mobile():
    # 플로팅 버튼이 본문 가리지 않게 — 모바일 아이콘 FAB로 축소 + 라벨 래핑
    assert 'class="fb-label"' in BASE
    assert "#fbWrap #fbBtn .fb-label { display: none; }" in CONSOLE_CSS
    assert "padding-bottom: 84px;" in CONSOLE_CSS


def test_collect_history_renders(client):
    assert client.get("/seller/collect/history").status_code == 200
