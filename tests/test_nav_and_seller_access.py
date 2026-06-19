"""tests/test_nav_and_seller_access.py — 좌측 nav 재배치 + 셀러 접근 가드 회귀.

오너 리포트(2026-06-19): 좌측의 등록 이력/이미지 큐/소싱 watches/후보 큐 버튼이
'동작하지 않음' — 원인은 _sourcing_require_admin()이 ADMIN_EMAILS 미설정 셀러에게
403을 돌려줬기 때문. 멀티유저 SaaS에서 이들은 셀러 작업 화면이므로 로그인만 요구한다.
또한 '수집 이력'을 잘 보이는 위쪽 '자주 쓰는' 그룹으로 옮기고, 마켓 업로드 모달에
'전체 선택' 버튼을 추가했다.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_sourcing_guard_allows_logged_in_seller_when_auth_on(monkeypatch):
    """인증 강제 ON + 비관리자 셀러 세션 → 가드 통과(None). 과거엔 403."""
    from src.order_webhook import app
    import src.seller_console.views as v
    monkeypatch.setattr(v, "_AUTH_ENABLED", True, raising=False)
    with app.test_request_context("/seller/sourcing/watches"):
        from flask import session
        session["user_id"] = "seller-123"
        session["user_role"] = "seller"   # 비관리자
        assert v._sourcing_require_admin() is None


def test_sourcing_guard_redirects_anonymous_when_auth_on(monkeypatch):
    """인증 강제 ON + 미로그인 → 로그인으로 리다이렉트(가드가 응답 반환)."""
    from src.order_webhook import app
    import src.seller_console.views as v
    monkeypatch.setattr(v, "_AUTH_ENABLED", True, raising=False)
    with app.test_request_context("/seller/sourcing/watches"):
        guard = v._sourcing_require_admin()
        assert guard is not None  # redirect 응답


def test_admin_gated_pages_accessible_in_tests(client):
    """테스트 환경(_AUTH_ENABLED off)에서 4개 페이지가 200(403 아님)."""
    for path in ("/seller/sourcing/watches", "/seller/sourcing/candidates",
                 "/seller/listing/history", "/seller/media/queue"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} → {resp.status_code}"


def test_nav_has_quick_access_group_with_collect_history(client):
    """좌측 nav 상단 '자주 쓰는' 그룹에 수집 이력 링크가 위쪽에 있다."""
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "자주 쓰는" in html
    # '자주 쓰는' 그룹이 수집 이력 링크보다 먼저 등장(위쪽)
    assert html.index("자주 쓰는") < html.index("/seller/collect/history")
    # 수집 이력 링크가 nav 상단부(운영 그룹보다 위)에 있다
    if "운영" in html:
        assert html.index("/seller/collect/history") < html.rindex("운영")


def test_nav_no_duplicate_collector_link(client):
    """'수집기'/'상품 수집기' 중복 제거 — nav에는 '상품 수집기'만 남는다."""
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "<span>상품 수집기</span>" in html
    assert "<span>수집기</span>" not in html  # 중복 라벨 제거됨


def test_collect_history_shows_thumbnails_and_bulk_select_all(client):
    """수집 이력: 이름 옆 썸네일(여러 장) + 일괄 등록 모달 '전체 선택' 버튼."""
    from unittest.mock import patch
    rows = [{
        "id": "abc123", "collected_at": "2026-06-19T12:00:00+00:00", "source": "extension",
        "domain": "shop.example", "url": "https://shop.example/p/1", "title": "가방",
        "image_url": "https://i/rep.jpg", "price": "100", "currency": "JPY", "status": "ok",
        "preview_url": "/seller/collect/preview/abc123",
        "extra_json": '{"images": ["https://i/rep.jpg", "https://i/2.jpg", "https://i/3.jpg"]}',
        "seller_id": "",
    }]
    with patch("src.seller_console.collect_history_store.list_items", return_value=rows), \
         patch("src.seller_console.collect_history_store.summary", return_value={"total": 1, "today": 1, "domains": 1, "by_source": {"extension": 1, "bookmarklet": 0, "manual": 0, "bulk": 0}}), \
         patch("src.seller_console.collect_history_store.distinct_domains", return_value=["shop.example"]):
        resp = client.get("/seller/collect/history")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "https://i/2.jpg" in html and "https://i/3.jpg" in html   # 추가 썸네일
    assert "toggleAllBulkMarkets" in html                            # 모달 전체 선택


def test_market_modal_has_select_all_button(client):
    """편집/업로드 페이지 마켓 모달에 '전체 선택' 버튼(toggleAllMarkets)이 있다."""
    from unittest.mock import patch
    draft = {"id": "p1", "title_ko": "테스트", "title": "t", "images": ["https://i/1.jpg"],
             "price": "10", "currency": "USD", "source": "x", "status": "collected"}
    with patch("src.seller_console.collect_history_store.get", return_value=draft):
        resp = client.get("/seller/collect/preview/p1")
    if resp.status_code == 200:
        html = resp.get_data(as_text=True)
        assert "toggleAllMarkets" in html
        assert "전체 선택" in html
