"""tests/test_collect_quick_bookmarklet.py — 토큰 없는 새 탭 네비게이션 북마클릿 수집."""
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


def _draft(**over):
    d = {"title_ko": "테스트", "title": "t", "title_en": "t", "images": ["https://i/1.jpg"],
         "price_original": "10", "price": "10", "currency": "USD", "source": "x"}
    d.update(over)
    return d


def test_quick_collect_saves_and_shows_confirmation(client):
    """편집페이지로 redirect하지 않고 '수집됨' 확인만 표시(내 계정에서 확인)."""
    with patch("src.seller_console.views._collect_real_draft", return_value=_draft()), \
         patch("src.seller_console.collect_history_store.append", return_value="qid1"):
        r = client.get("/seller/collect/quick?u=https://shop.example/p/1")
    assert r.status_code == 200
    assert "수집 완료" in r.get_data(as_text=True)


def test_quick_collect_meta_fallback_when_server_blocked(client):
    """서버 수집 실패해도 북마클릿이 보낸 페이지 메타로 최소 수집(정직)."""
    with patch("src.seller_console.views._collect_real_draft", return_value=None), \
         patch("src.seller_console.collect_history_store.append", return_value="qid2") as ap:
        r = client.get("/seller/collect/quick?u=https://shop.example/p/2&t=가방&img=https://i/x.jpg&p=99&c=USD")
    assert r.status_code == 200
    assert "수집 완료" in r.get_data(as_text=True)
    # append가 메타 기반으로 호출됨
    assert ap.call_count == 1
    assert ap.call_args.kwargs["title"] == "가방"
    assert ap.call_args.kwargs["source"] == "bookmarklet"


def test_quick_collect_no_data_shows_honest_result(client):
    with patch("src.seller_console.views._collect_real_draft", return_value=None):
        r = client.get("/seller/collect/quick?u=https://shop.example/p/3")
    assert r.status_code == 200
    assert "자동 수집이 어려운" in r.get_data(as_text=True)


def test_quick_collect_rejects_bad_url(client):
    r = client.get("/seller/collect/quick?u=notaurl")
    assert r.status_code == 400


def test_bookmarklet_page_inpage_no_new_window(client):
    # v38 #5: 새 창 금지 → 내 토큰 백그라운드 fetch + 인페이지 토스트로 전환.
    html = client.get("/seller/bookmarklet").get_data(as_text=True)
    assert "window.open" not in html            # 새 창/팝업 0
    assert "/api/v1/collect/extension" in html  # 백그라운드 fetch
    assert "Bearer" in html                     # 내 토큰 인증
    assert "고가수집기" in html                  # 라벨


def test_collect_page_amazon_dropdown_and_favicon(client):
    html = client.get("/seller/collect").get_data(as_text=True)
    assert "dropdown-toggle" in html
    assert "amazon.co.jp" in html and "amazon.de" in html
    assert "favicon.svg" in html
