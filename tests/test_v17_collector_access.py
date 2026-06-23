"""tests/test_v17_collector_access.py — v17: 개발안내 숨김·진입 수집기 보장·소싱처 칩·북마클릿."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---- P0-1: api-status 관리자 전용 + 개발문구 숨김 ----
def test_api_status_admin_only(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"; s["user_email"] = "u@x.com"; s["user_role"] = "seller"
    assert client.get("/seller/api-status").status_code == 302         # 비관리자 리다이렉트
    assert client.get("/seller/api-status/json").status_code == 403
    # 일반 유저 화면에 api-status 링크/개발 안내 미노출
    coll = client.get("/seller/collect").get_data(as_text=True)
    assert "API 상태" not in coll
    dash = client.get("/seller/dashboard").get_data(as_text=True)
    assert "API 연결 상태" not in dash


def test_api_status_admin_ok_no_proxy_commerce(client):
    with client.session_transaction() as s:
        s["user_id"] = "a1"; s["user_email"] = "a@x.com"; s["user_role"] = "admin"
    r = client.get("/seller/api-status")
    assert r.status_code == 200
    assert "proxy-commerce" not in r.get_data(as_text=True)


# ---- P0-2: 앱 진입 마커 + 수집기 강제 노출 ----
def test_entry_marker_on_chips(client):
    html = client.get("/seller/collect").get_data(as_text=True)
    assert "kgpsrc=app" in html        # 마켓 칩에 진입 마커


def test_content_script_entry_session():
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "kgpEntrySession" in cs and "kgpsrc=app" in cs
    assert "kgp_entry" in cs            # sessionStorage 유지
    # FAB off여도 진입 세션이면 노출 + 호스트 게이트도 진입 세션 허용
    assert "!KGP_FAB_ENABLED && !kgpEntrySession()" in cs
    assert "!kgpHostAllowed() && !kgpEntrySession()" in cs


# ---- P1: 등록 소싱처 칩 + 북마클릿 비교표 ----
def test_my_sources_chip_renders(client, monkeypatch):
    import src.seller_console.my_sources_store as ms
    monkeypatch.setattr(ms, "list_sources", lambda: [{"domain": "yoshidakaban.com", "label": "요시다카반"}])
    html = client.get("/seller/collect").get_data(as_text=True)
    assert "yoshidakaban.com" in html and "요시다카반" in html
    assert "my-source-chip" in html


def test_bookmarklet_comparison_table(client):
    html = client.get("/seller/bookmarklet").get_data(as_text=True)
    assert "크롬 확장 vs 북마클릿" in html
    assert "<table" in html and "메인·권장" in html
