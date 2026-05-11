"""tests/test_me_notifications_route.py — /seller/me/notifications 라우트 hotfix 테스트 (Phase 148).

Phase 147에서 /seller/me/notifications 라우트를 정의했으나,
사이드바 매트릭스 테스트가 이를 누락했던 회귀를 방지한다.
"""
from __future__ import annotations

import os
import pytest


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture(scope="module")
def client(app):
    with app.test_client() as c:
        yield c


def test_me_notifications_route_registered(app):
    """/seller/me/notifications 엔드포인트가 Flask에 등록되어야 한다."""
    assert "seller_console.me_notifications" in app.view_functions, (
        "/seller/me/notifications (seller_console.me_notifications) 라우트가 등록되지 않았습니다"
    )


def test_me_notifications_route_not_404(client):
    """/seller/me/notifications 경로가 404를 반환하지 않아야 한다."""
    resp = client.get("/seller/me/notifications")
    assert resp.status_code != 404, (
        f"/seller/me/notifications이 404를 반환합니다 (status={resp.status_code})"
    )


def test_me_notifications_subscribe_route_registered(app):
    """/seller/me/notifications/subscribe POST 엔드포인트가 등록되어야 한다."""
    assert "seller_console.me_notifications_subscribe" in app.view_functions


def test_me_notifications_unsubscribe_route_registered(app):
    """/seller/me/notifications/unsubscribe POST 엔드포인트가 등록되어야 한다."""
    assert "seller_console.me_notifications_unsubscribe" in app.view_functions


def test_me_notifications_in_sidebar_links(client):
    """/seller/me/notifications 링크가 셀러 대시보드 사이드바에 포함되어야 한다."""
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/me/notifications" in html, (
        "사이드바에 /seller/me/notifications 링크가 없습니다"
    )


def test_me_notifications_subscribe_returns_json(client):
    """subscribe API가 JSON을 반환해야 한다."""
    resp = client.post(
        "/seller/me/notifications/subscribe",
        json={"subscription": {"endpoint": "", "keys": {}}},
    )
    data = resp.get_json()
    assert data is not None
    assert "ok" in data


def test_me_notifications_test_returns_json(client):
    """test API가 JSON을 반환해야 한다."""
    resp = client.post("/seller/me/notifications/test")
    assert resp.content_type.startswith("application/json")
