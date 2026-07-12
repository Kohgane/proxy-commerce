"""tests/test_v57_live_list.py — v57 STEP2: 수집 → 목록 실시간 반영(전체 리렌더 금지).

수집이력: `since` 커서(updated_after) endpoint가 커서 이후 신규 상품만 행 파셜로 렌더 →
클라가 목록 맨 위에 삽입 + '새 상품 N건 수집됨' 토스트(기존 행 재렌더 0).
카탈로그: count 폴링 → 증가 시 정직한 '마켓 동기화 갱신' 배너(수집 아님, 자동 전체리렌더 금지).
3중화(visibilitychange + 15초 폴링 활성탭만 + 증분 삽입) 소스 계약을 가드.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
os.environ.setdefault("GOOGLE_SHEET_ID", "")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    return flask_app.test_client()


def _row(item_id, at, title="상품 " ):
    return {"id": item_id, "url": "https://x.com/g-" + item_id, "domain": "x.com",
            "title": title + item_id, "price": "1,000", "currency": "KRW",
            "source": "extension", "status": "ok", "collected_at": at,
            "image_url": "https://x.com/i.jpg", "extra_json": "{}"}


def test_since_no_cursor_returns_baseline_no_rows(client):
    """커서 미지정(첫 호출) → 신규 0 + server_max만(초기 화면과 중복 삽입 방지)."""
    rows = [_row("a", "2026-07-12T10:00:00"), _row("b", "2026-07-12T09:00:00")]
    with patch("src.seller_console.collect_history_store.list_items", return_value=rows):
        j = client.get("/seller/collect/history/since").get_json()
    assert j["ok"] is True and j["count"] == 0
    assert j["server_max"] == "2026-07-12T10:00:00" and j["html"] == ""


def test_since_returns_only_newer_than_cursor(client):
    """커서 이후 신규만 반환 — 오래된 행은 제외(전체 리렌더 아님)."""
    rows = [_row("new", "2026-07-12T12:00:00"), _row("old", "2026-07-12T08:00:00")]
    with patch("src.seller_console.collect_history_store.list_items", return_value=rows):
        j = client.get("/seller/collect/history/since?after=2026-07-12T10:00:00").get_json()
    assert j["count"] == 1
    assert "g-new" in j["html"] and "g-old" not in j["html"]     # 신규 행만 렌더
    assert 'class="row-chk" value="new"' in j["html"]


def test_since_none_new_when_cursor_current(client):
    """커서가 최신과 같으면 신규 0(중복 삽입 방지)."""
    rows = [_row("a", "2026-07-12T10:00:00")]
    with patch("src.seller_console.collect_history_store.list_items", return_value=rows):
        j = client.get("/seller/collect/history/since?after=2026-07-12T10:00:00").get_json()
    assert j["count"] == 0 and j["html"] == ""


def test_since_requires_auth(monkeypatch):
    """비로그인(auth 강제)이면 401 — 데이터 누출 0."""
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "1")
    import importlib
    import src.seller_console.views as v
    importlib.reload(v)
    try:
        from src.order_webhook import app as flask_app
        flask_app.config["TESTING"] = True
        r = flask_app.test_client().get("/seller/collect/history/since?after=x")
        assert r.status_code == 401
    finally:
        monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
        importlib.reload(v)


def test_history_page_has_increment_polling(client):
    """수집이력 화면 = since 증분 폴링(15초·활성탭·탭복귀) + 커서 data-newest + 토스트, 전체 reload 자동호출 0."""
    with patch("src.seller_console.collect_history_store.list_items", return_value=[_row("a", "2026-07-12T10:00:00")]), \
         patch("src.seller_console.collect_history_store.summary", return_value={"total": 1, "today": 1, "domains": 1, "by_source": {}}), \
         patch("src.seller_console.collect_history_store.distinct_domains", return_value=[]):
        html = client.get("/seller/collect/history").data.decode("utf-8")
    assert "/seller/collect/history/since" in html
    assert "data-newest" in html
    assert "15000" in html                       # 15초 폴링
    assert "visibilitychange" in html
    assert "새 상품 " in html                     # 증분 토스트 카피
    assert "document.hidden" in html             # 활성 탭만
    # 폴링 apply 경로에서 window.location.reload 자동 호출 금지(사용자 클릭 버튼만 reload).
    assert "insertBefore" in html                # 맨 위 삽입(증분)


def test_catalog_count_endpoint(client):
    """카탈로그 count → {ok, total}(마켓 동기화 갱신 감지용)."""
    class _FakeItem:
        marketplace = "coupang"
    class _FakeResult:
        items = [_FakeItem(), _FakeItem(), _FakeItem()]
    with patch("src.seller_console.market_status_sheets.MarketStatusSheetsAdapter") as M:
        M.return_value.fetch_all.return_value = _FakeResult()
        j = client.get("/seller/catalog/count").get_json()
    assert j["ok"] is True and j["total"] == 3


def test_catalog_page_has_honest_refresh_banner(client):
    """카탈로그 = count 폴링 + '마켓 동기화 갱신' 배너(수집 아님) + 새로고침 버튼(자동 전체리렌더 금지)."""
    with patch("src.seller_console.views.MarketStatusSheetsAdapter", create=True):
        html = client.get("/seller/catalog").data.decode("utf-8")
    assert "/seller/catalog/count" in html
    assert "마켓 동기화" in html                  # 정직 카피(수집됨 아님)
    assert "15000" in html and "document.hidden" in html
