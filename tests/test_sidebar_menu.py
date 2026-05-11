from __future__ import annotations

import os

import pytest


SELLER_MENU_LINKS = [
    "/seller/dashboard",
    "/seller/manual-collect",
    "/seller/margin",
    "/seller/markets",
    "/seller/catalog",
    "/seller/orders",
    "/seller/notifications",
    "/seller/cs/messaging",
    "/seller/cs/autoreply",
    "/seller/api/status",
    "/seller/me",
    "/seller/api/tokens",
    "/seller/bookmarklet",
    "/seller/discovery",
    "/seller/collect-history",
    "/seller/pricing/rules",
    "/seller/pricing/competitors",
    "/seller/pricing/fx-impact",
    "/seller/analytics",
    "/seller/inventory/reorder",
    "/seller/marketing/campaigns",
    "/seller/sourcing/watches",
    "/seller/sourcing/candidates",
    "/seller/listing/history",
    "/seller/media/queue",
    "/seller/ads/campaigns",
    "/seller/ads/keywords",
]


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import src.order_webhook as wh

    wh.app.config["TESTING"] = True
    return wh.app


def test_seller_dashboard_contains_phase_links(client):
    resp = client.get("/seller/dashboard")
    html = resp.get_data(as_text=True)
    for url in SELLER_MENU_LINKS:
        assert url in html


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


def test_admin_diagnostics_contains_admin_menu(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "admin-user"
        sess["user_role"] = "admin"
    resp = client.get("/admin/diagnostics")
    html = resp.get_data(as_text=True)
    for label in ("대시보드", "상품 목록", "주문 목록", "재고 현황", "진단", "사용자 관리", "환경변수", "로그"):
        assert label in html


def test_seller_page_does_not_show_admin_sidebar_items(client):
    resp = client.get("/seller/dashboard")
    html = resp.get_data(as_text=True)
    assert "/admin/products" not in html
    assert "/admin/orders" not in html
    assert "/admin/inventory" not in html
