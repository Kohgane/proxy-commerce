from __future__ import annotations

import os

import pytest


SIDEBAR_LINKS = [
    "/seller/dashboard",
    "/seller/manual-collect",
    "/seller/margin",
    "/seller/markets",
    "/seller/orders",
    "/seller/orders/auto",
    "/seller/inventory/reorder",
    "/seller/notifications",
    "/seller/catalog",
    "/seller/sourcing/watches",
    "/seller/sourcing/candidates",
    "/seller/listing/history",
    "/seller/media/queue",
    "/seller/pricing/rules",
    "/seller/pricing/competitors",
    "/seller/pricing/fx-impact",
    "/seller/marketing/campaigns",
    "/seller/ads/campaigns",
    "/seller/ads/keywords",
    "/seller/analytics",
    "/seller/collect-history",
    "/seller/shipping/tracking",
    "/seller/settlement",
    "/seller/cs/messaging",
    "/seller/cs/autoreply",
    "/seller/cs/inbox",
    "/seller/returns/inbox",
    "/seller/api/status",
    "/seller/me",
    "/seller/api/tokens",
    "/seller/bookmarklet",
    "/seller/discovery",
]


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


def test_sidebar_menu_links_exist_in_dashboard_html(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    for url in SIDEBAR_LINKS:
        assert url in html, f"사이드바 메뉴에 {url}이 누락"


@pytest.mark.parametrize("path", SIDEBAR_LINKS)
def test_sidebar_link_route_is_not_404(client, path):
    resp = client.get(path)
    assert resp.status_code != 404, f"사이드바 메뉴 {path}는 존재하지만 라우트가 404"
