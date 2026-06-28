"""tests/test_v35_landing_chrome.py — v35 P0: 랜딩 상단 정리(헤더 1개·흰여백0·관리자링크 비노출)."""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ROOT_REDIRECT", "landing")
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    app.secret_key = "test-v35-landing"
    with app.test_client() as c:
        yield c


def test_landing_suppresses_generic_topnav(client):
    html = client.get("/").get_data(as_text=True)
    # 공통 dark topnav(navbar-dark bg-dark)·맨텍스트 메뉴 미노출 → 랜딩 자체 .lpnav 단일 헤더
    assert "navbar-dark bg-dark" not in html
    assert "lpnav" in html
    # 일반(비로그인) 유저에게 관리자/시스템상태 링크 비노출
    assert 'href="/admin/"' not in html
    assert 'href="/health/deep"' not in html
    # 푸터 법적 링크는 랜딩 자체 푸터로 유지(개인정보·약관)
    assert 'href="/privacy"' in html and 'href="/terms"' in html


def test_landing_main_full_bleed(client):
    html = client.get("/").get_data(as_text=True)
    # 히어로가 상단에 바로 붙도록 메인 컨테이너 패딩(container-fluid py-4) 제거
    assert '<main class="container-fluid py-4">' not in html


def _topnav_region(html: str) -> str:
    """공통 topnav <nav>…</nav> 영역만 추출(404 본문의 동명 링크와 분리)."""
    start = html.find('class="navbar navbar-expand-lg navbar-dark')
    if start < 0:
        return ""
    end = html.find("</nav>", start)
    return html[start:end if end > 0 else start + 2000]


def test_topnav_admin_links_hidden_for_seller(client):
    # 셀러(비관리자) 세션: 공통 topnav에 관리자/API 문서/시스템 상태 운영 링크 비노출
    with client.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_role"] = "seller"
    nav = _topnav_region(client.get("/nonexistent-404-page").get_data(as_text=True))
    assert nav, "공통 topnav가 렌더되지 않음(트리비얼 통과 방지)"
    assert "관리자" not in nav
    assert "API 문서" not in nav
    assert "시스템 상태" not in nav
    assert "셀러 콘솔" in nav                    # 셀러 메뉴는 유지


def test_topnav_admin_links_visible_for_admin(client):
    with client.session_transaction() as s:
        s["user_id"] = "admin1"
        s["user_role"] = "admin"
    nav = _topnav_region(client.get("/nonexistent-404-page").get_data(as_text=True))
    assert "관리자" in nav
    assert "API 문서" in nav
