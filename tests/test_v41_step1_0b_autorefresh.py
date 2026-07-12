"""tests/test_v41_step1_0b_autorefresh.py — v41 STEP 1-0b: 수집 → 목록 자동 반영.

수집이력 화면이 열려 있으면 새로고침 없이 새 상품이 등장해야 한다(폴링/탭포커스 재조회).
정직 데이터: 자동 반영은 '서버에 실제로 영속 저장된' 총건수(count 엔드포인트)가 늘었을 때만.
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


def _summary(total):
    return {"total": total, "today": total, "domains": 1,
            "by_source": {"extension": total, "bookmarklet": 0, "manual": 0, "bulk": 0}}


def test_count_endpoint_returns_total(client):
    """GET /seller/collect/history/count → {ok, total} 실 집계."""
    with patch("src.seller_console.collect_history_store.summary", return_value=_summary(3)):
        r = client.get("/seller/collect/history/count")
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True and j["total"] == 3


def test_count_reflects_new_collect(client):
    """수집으로 저장이 늘면 count도 늘어난다(자동 반영의 근거)."""
    with patch("src.seller_console.collect_history_store.summary", return_value=_summary(1)):
        before = client.get("/seller/collect/history/count").get_json()["total"]
    with patch("src.seller_console.collect_history_store.summary", return_value=_summary(2)):
        after = client.get("/seller/collect/history/count").get_json()["total"]
    assert after == before + 1


def test_count_respects_days_param(client):
    """days 파라미터가 summary로 전달돼 화면 필터와 일치(비교 오차 0)."""
    with patch("src.seller_console.collect_history_store.summary", return_value=_summary(5)) as m:
        r = client.get("/seller/collect/history/count?days=7")
    assert r.status_code == 200
    assert m.call_args.kwargs.get("days") == 7


def test_count_honest_on_error(client):
    """조회 실패 시 가짜 숫자 금지 → ok:false."""
    with patch("src.seller_console.collect_history_store.summary", side_effect=RuntimeError("boom")):
        r = client.get("/seller/collect/history/count")
    assert r.status_code == 200
    assert r.get_json()["ok"] is False


def test_history_page_has_polling_script(client):
    """수집이력 화면에 실시간 반영 폴링 스크립트가 포함(v57: since 증분 + 탭포커스).
    (v41 count 폴링 → v57 STEP2 since 커서 증분 삽입으로 승격, 전체 리렌더 제거.)"""
    with patch("src.seller_console.collect_history_store.list_items", return_value=[]), \
         patch("src.seller_console.collect_history_store.summary", return_value=_summary(0)), \
         patch("src.seller_console.collect_history_store.distinct_domains", return_value=[]):
        html = client.get("/seller/collect/history").data.decode("utf-8")
    assert "/seller/collect/history/since" in html
    assert "visibilitychange" in html
    assert "STEP2" in html


def test_autorefresh_guards_editing(client):
    """편집 중(드로어/모달) 중단 방지 가드가 스크립트에 존재(정직 UX)."""
    with patch("src.seller_console.collect_history_store.list_items", return_value=[]), \
         patch("src.seller_console.collect_history_store.summary", return_value=_summary(0)), \
         patch("src.seller_console.collect_history_store.distinct_domains", return_value=[]):
        html = client.get("/seller/collect/history").data.decode("utf-8")
    assert "kgp-drawer-open" in html and "modal.show" in html
