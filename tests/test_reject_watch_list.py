"""tests/test_reject_watch_list.py — 반려 감시 대상 목록(읽기 전용).

**왜 필요했나(실측 2026-09-04):** 감시 목록은 **POST로 빈 폼을 제출해야만** 읽혔고, 그것도
쿠팡 자격이 있을 때 라이브 조회의 *입력*으로만 쓰였다. 자격이 없으면 오류 문구만 떠서
**크론이 뭘 감시 중인지 볼 방법이 아예 없었다** — 감시가 블랙박스였다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
TPL = Path("src/seller_console/templates/reject_watch.html").read_text(encoding="utf-8")

ROWS = [
    {"sid": "16369251981", "title": "ALPAKA 에어 슬링 크로스백", "account": "gogane",
     "market_url": "https://www.coupang.com/vp/products/1"},
    {"sid": "16369251982", "title": "", "account": "gogane", "market_url": ""},
]


@pytest.fixture
def client():
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
        yield c


def test_get_renders_watch_list_without_posting(client):
    """★ GET만으로 감시 대상이 보인다 — 폼을 제출할 필요도, 쿠팡 자격도 필요 없다."""
    with patch("src.db.market_registrations_pg.watch_queue", return_value=ROWS):
        html = client.get("/seller/sourcing/reject-watch").get_data(as_text=True)
    assert "16369251981" in html and "ALPAKA 에어 슬링 크로스백" in html
    assert "(제목 없음)" in html                       # 제목 빈 건도 행을 잃지 않는다
    assert "감시 대상" in html


def test_ledger_read_does_not_call_coupang():
    """대장 조회는 쿠팡 API를 안 부른다 — 자격이 없어도 목록은 떠야 한다."""
    from src.seller_console.views import _reject_watch_queue
    with patch("src.db.market_registrations_pg.watch_queue", return_value=ROWS) as q, \
         patch("src.uploaders.coupang_uploader.CoupangUploader.get_status_histories") as api:
        out = _reject_watch_queue("gogane")
    assert out["connected"] is True and len(out["rows"]) == 2
    q.assert_called_once()
    api.assert_not_called()


def test_unreadable_ledger_is_honest_not_zero(client):
    """★ '0건'과 '못 읽음'을 구분한다 — 빈 목록을 찍으면 '감시 대상 없음'으로 오독된다."""
    with patch("src.db.market_registrations_pg.watch_queue", side_effect=RuntimeError("boom")):
        html = client.get("/seller/sourcing/reject-watch").get_data(as_text=True)
    assert "등록 대장을 읽지 못했습니다" in html
    assert "감시 대상이 없어요" not in html


def test_empty_ledger_says_empty(client):
    with patch("src.db.market_registrations_pg.watch_queue", return_value=[]):
        html = client.get("/seller/sourcing/reject-watch").get_data(as_text=True)
    assert "감시 대상이 없어요" in html


def test_textarea_is_placeholder_not_prefilled(client):
    """★ 오조회 지뢰 점검: 예시 번호가 **실값으로 프리필되면** 엉뚱한 상품을 조회하게 된다."""
    with patch("src.db.market_registrations_pg.watch_queue", return_value=[]):
        html = client.get("/seller/sourcing/reject-watch").get_data(as_text=True)
    body = re.search(r'<textarea[^>]*id="sids"[^>]*>(.*?)</textarea>', html, re.S)
    assert body and body.group(1).strip() == ""        # 실값 0
    assert 'placeholder="123456789' in html            # 예시는 placeholder로만


def test_single_source_for_the_queue():
    """판정기 2개 금지 — 화면이 보여준 목록과 조회가 쓰는 목록이 같은 함수에서 나온다."""
    assert VIEWS.count("REG.watch_queue(") == 1
    assert "_reject_watch_queue(account)" in VIEWS
    assert 'sids = [q["sid"] for q in watch["rows"]]' in VIEWS


def test_read_only_no_write_actions():
    """읽기 전용 — 이 표에서 처방을 실행하지 않는다(비가역 작업은 오너 승인 게이트 뒤)."""
    block = TPL.split("감시 대상")[1].split("<!-- 입력 -->")[0]
    assert "<form" not in block and "method=\"post\"" not in block
